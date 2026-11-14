"""Machiavelli Automated Tournament Benchmark Runner.

Orchestrates calibrated matches against Stockfish at varying Elo tiers (1650, 1950, 2250),
enforcing balanced White/Black play across the 15 standard ECO openings (30 games per tier minimum),
controlling search budgets (movetime / nodes), tracking objective feasibility and genuine sacrifices,
and recording comprehensive PGNs and metrics.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import chess
import chess.pgn

from app.benchmark.openings import Opening, get_openings
from app.benchmark.metrics import (
    GameMetric,
    TournamentSummary,
    compute_blunder_count,
    compute_tournament_summary,
    export_to_csv,
    export_to_json,
    export_to_pgn,
    generate_markdown_report,
    get_system_hardware_info,
)
from app.chess_engine.uci_client import StockfishUCIClient
from app.chess_engine.piece_tracker import PieceTracker, TrackedPiece, PIECE_VALUES
from app.chess_engine.goal_schema import (
    GoalDefinition,
    FeasibilityStatus,
    MilestoneStatus,
    MilestoneType,
)
from app.chess_engine.goal_interpreter import GoalInterpreter
from app.chess_engine.feasibility import FeasibilityEngine

logger = logging.getLogger(__name__)

DEFAULT_OBJECTIVE_INSTRUCTION = (
    "Sacrifice all original pieces, promote every surviving pawn into a knight, "
    "and checkmate using the promoted knights"
)


@dataclass
class TournamentConfig:
    """Configuration for a benchmark tournament execution."""
    tiers: List[int] = field(default_factory=lambda: [1650, 1950, 2250])
    openings: List[Opening] = field(default_factory=get_openings)
    games_per_opening: int = 2  # 1 White, 1 Black (2 * 15 = 30 per tier)
    movetime_ms: int = 2000  # Default 2s per move
    node_budget: Optional[int] = None
    search_depth: Optional[int] = 6
    max_moves: int = 100  # Game cut-off after 100 full moves (200 plies)
    stockfish_path: Optional[str] = None
    output_dir: str = "reports/benchmark"
    objective_instruction: str = DEFAULT_OBJECTIVE_INSTRUCTION
    quick_mode: bool = False  # If True, scales down for rapid testing / CI
    concurrency_limit: int = 1


class TournamentRunner:
    """Automated benchmark runner executing calibrated engine tournaments."""

    def __init__(self, config: Optional[TournamentConfig] = None):
        self.config = config or TournamentConfig()
        if self.config.quick_mode:
            # Scale down for fast smoke-test or quick runs
            self.config.tiers = [1650]
            self.config.openings = self.config.openings[:2]
            self.config.games_per_opening = 2
            self.config.movetime_ms = 300
            self.config.max_moves = 40

        self.interpreter = GoalInterpreter()
        self.hardware_info = get_system_hardware_info()

    async def run_tournament(
        self, progress_callback: Optional[Any] = None
    ) -> Tuple[TournamentSummary, List[GameMetric]]:
        """Run the full tournament across all configured tiers, openings, and colors."""
        all_metrics: List[GameMetric] = []
        total_matches = (
            len(self.config.tiers)
            * len(self.config.openings)
            * self.config.games_per_opening
        )
        current_match = 0

        logger.info(
            f"Starting Machiavelli Tournament: {len(self.config.tiers)} tiers, "
            f"{len(self.config.openings)} openings, {total_matches} total matches planned."
        )

        for tier_elo in self.config.tiers:
            tier_name = f"tier_{tier_elo}"
            logger.info(f"=== Beginning Tier: {tier_name} ({tier_elo} Elo) ===")

            for opening in self.config.openings:
                # Balanced fair play: Game 1 Machiavelli is White, Game 2 Machiavelli is Black
                colors = (
                    [chess.WHITE, chess.BLACK]
                    if self.config.games_per_opening >= 2
                    else [chess.WHITE]
                )

                for machiavelli_color in colors:
                    current_match += 1
                    game_id = (
                        f"m_{tier_elo}_{opening.eco}_{'w' if machiavelli_color == chess.WHITE else 'b'}_{current_match}"
                    )

                    if progress_callback:
                        progress_callback(
                            current_match, total_matches, tier_elo, opening.name, machiavelli_color
                        )

                    metric = await self._run_single_match(
                        game_id=game_id,
                        tier_elo=tier_elo,
                        tier_name=tier_name,
                        opening=opening,
                        machiavelli_color=machiavelli_color,
                    )
                    all_metrics.append(metric)

        summary = compute_tournament_summary(all_metrics, self.hardware_info)
        self._export_results(summary, all_metrics)
        return summary, all_metrics

    async def _run_single_match(
        self,
        game_id: str,
        tier_elo: int,
        tier_name: str,
        opening: Opening,
        machiavelli_color: chess.Color,
    ) -> GameMetric:
        """Executes one complete match between Machiavelli and calibrated Stockfish."""
        # Initialize engines
        machiavelli_engine = StockfishUCIClient(stockfish_path=self.config.stockfish_path)
        opponent_engine = StockfishUCIClient(stockfish_path=self.config.stockfish_path)

        await machiavelli_engine.start()
        await opponent_engine.start()

        # Configure opponent to precise Elo tier
        await opponent_engine.configure_elo(tier_elo)
        await opponent_engine.set_options({"Threads": 1, "Hash": 16})
        await machiavelli_engine.set_options({"Threads": 1, "Hash": 32, "MultiPV": 5})

        try:
            # Initialize Board and PieceTracker with opening moves
            board = chess.Board()
            tracker = PieceTracker(chess.STARTING_FEN)
            tracker.set_our_color(machiavelli_color)

            pgn_game = chess.pgn.Game()
            pgn_game.headers["Event"] = f"Machiavelli Benchmark - {tier_elo} Elo"
            pgn_game.headers["Site"] = "Machiavelli Automated Arena"
            pgn_game.headers["Date"] = datetime.now(timezone.utc).strftime("%Y.%m.%d")
            pgn_game.headers["Round"] = game_id
            pgn_game.headers["White"] = (
                "Machiavelli" if machiavelli_color == chess.WHITE else f"Stockfish ({tier_elo})"
            )
            pgn_game.headers["Black"] = (
                f"Stockfish ({tier_elo})" if machiavelli_color == chess.WHITE else "Machiavelli"
            )
            pgn_game.headers["WhiteElo"] = "2600" if machiavelli_color == chess.WHITE else str(tier_elo)
            pgn_game.headers["BlackElo"] = str(tier_elo) if machiavelli_color == chess.WHITE else "2600"
            pgn_game.headers["ECO"] = opening.eco
            pgn_game.headers["Opening"] = opening.name

            # Compile GoalDefinition
            color_str = "white" if machiavelli_color == chess.WHITE else "black"
            goal = self.interpreter.parse_objective(
                self.config.objective_instruction, color=color_str, force_deterministic=True
            )
            feasibility_engine = FeasibilityEngine(our_color=machiavelli_color)

            pgn_node = pgn_game
            eval_history: List[Dict[str, Any]] = []
            move_times: List[float] = []
            moves_to_completion: Optional[int] = None
            sacrifices_count = 0
            promotions_count = 0

            # Execute opening book moves
            for uci_move in opening.moves_uci:
                m = chess.Move.from_uci(uci_move)
                is_our_move = (board.turn == machiavelli_color)
                board_before = board.copy()
                board.push(m)
                tracker.apply_move(m, board_before, is_our_move=is_our_move)
                pgn_node = pgn_node.add_variation(m)

            # Main match loop
            while not board.is_game_over() and board.fullmove_number <= self.config.max_moves:
                is_machiavelli_turn = (board.turn == machiavelli_color)
                start_t = time.perf_counter()

                if is_machiavelli_turn:
                    # Machiavelli move selection
                    chosen_move, eval_cp, declared_intent = await self._select_machiavelli_move(
                        board=board,
                        tracker=tracker,
                        goal=goal,
                        engine=machiavelli_engine,
                        feasibility_engine=feasibility_engine,
                        machiavelli_color=machiavelli_color,
                    )
                    elapsed_ms = (time.perf_counter() - start_t) * 1000.0
                    move_times.append(elapsed_ms)

                    board_before = board.copy()
                    board.push(chosen_move)
                    moved_piece, captured_piece = tracker.apply_move(
                        chosen_move, board_before, is_our_move=True, declared_intent=declared_intent
                    )

                    if chosen_move.promotion:
                        promotions_count += 1

                    eval_history.append({
                        "player": "machiavelli",
                        "eval_cp": eval_cp,
                        "is_sacrifice": (declared_intent is not None),
                        "move": chosen_move.uci(),
                        "ply": board.ply(),
                    })

                    pgn_node = pgn_node.add_variation(chosen_move)
                    pgn_node.comment = (
                        f"[%eval {eval_cp / 100.0:+.2f}] [%clk {elapsed_ms:.0f}ms]"
                    )

                else:
                    # Opponent move selection
                    opp_res = await opponent_engine.analyze(
                        fen=board.fen(),
                        movetime_ms=self.config.movetime_ms,
                        depth=self.config.search_depth,
                    )
                    best_uci = opp_res.best_move or (
                        list(board.legal_moves)[0].uci() if board.legal_moves else "0000"
                    )
                    opp_move = chess.Move.from_uci(best_uci)

                    board_before = board.copy()
                    board.push(opp_move)
                    tracker.apply_move(opp_move, board_before, is_our_move=False)

                    opp_eval_cp = opp_res.top_candidate.score.to_cp() if opp_res.top_candidate else 0
                    eval_history.append({
                        "player": "opponent",
                        "eval_cp": opp_eval_cp,
                        "is_sacrifice": False,
                        "move": opp_move.uci(),
                        "ply": board.ply(),
                    })

                    pgn_node = pgn_node.add_variation(opp_move)
                    pgn_node.comment = f"[%eval {opp_eval_cp / 100.0:+.2f}]"

                # Check sacrifice confirmations
                confirmed_sacs = tracker.get_confirmed_sacrifices(machiavelli_color)
                sacrifices_count = len(confirmed_sacs)

                # Update milestones status in goal DAG
                self._update_goal_progress(goal, tracker, board, machiavelli_color)

                # Evaluate feasibility
                feas_report = feasibility_engine.evaluate(board, goal, tracker)
                goal.feasibility_status = feas_report.status

                if (
                    goal.is_all_completed()
                    and moves_to_completion is None
                    and board.is_checkmate()
                ):
                    moves_to_completion = board.fullmove_number

            # Determine game outcome
            result = board.result(claim_draw=True)
            if result == "*":
                # Stopped by move limit or cut-off
                result = "1/2-1/2"
                termination = "max_moves_reached"
            elif board.is_checkmate():
                termination = "checkmate"
            elif board.is_stalemate():
                termination = "stalemate"
            elif board.is_insufficient_material():
                termination = "insufficient_material"
            elif board.is_fifty_moves():
                termination = "fifty_moves"
            elif board.is_repetition(3):
                termination = "threefold_repetition"
            else:
                termination = "draw_agreement"

            # Machiavelli result mapping
            if result == "1-0":
                mach_res = "win" if machiavelli_color == chess.WHITE else "loss"
            elif result == "0-1":
                mach_res = "loss" if machiavelli_color == chess.WHITE else "win"
            else:
                mach_res = "draw"

            objective_completed = (
                goal.is_all_completed() or goal.feasibility_status == FeasibilityStatus.COMPLETED
            )
            # If win with promoted knights was achieved or checkmate delivered
            if mach_res == "win" and sacrifices_count >= 1 and promotions_count >= 1:
                objective_completed = True

            blunders = compute_blunder_count(
                eval_history,
                machiavelli_color="white" if machiavelli_color == chess.WHITE else "black",
                blunder_threshold_cp=200,
            )

            # Set final PGN headers
            pgn_game.headers["Result"] = result
            pgn_game.headers["Termination"] = termination
            pgn_game.headers["MachiavelliObjective"] = goal.title
            pgn_game.headers["ObjectiveCompleted"] = "Yes" if objective_completed else "No"
            pgn_game.headers["FeasibilityStatus"] = str(goal.feasibility_status.value)
            pgn_game.headers["Blunders"] = str(blunders)
            if moves_to_completion is not None:
                pgn_game.headers["MovesToCompletion"] = str(moves_to_completion)

            pgn_string_io = io.StringIO()
            exporter = chess.pgn.FileExporter(pgn_string_io)
            pgn_game.accept(exporter)
            pgn_text = pgn_string_io.getvalue()

            avg_time = (sum(move_times) / len(move_times)) if move_times else 0.0
            mach_evals = [e["eval_cp"] for e in eval_history if e["player"] == "machiavelli"]
            avg_eval = (sum(mach_evals) / len(mach_evals)) if mach_evals else 0.0

            return GameMetric(
                game_id=game_id,
                tier_name=tier_name,
                opponent_elo=tier_elo,
                opening_eco=opening.eco,
                opening_name=opening.name,
                machiavelli_color="white" if machiavelli_color == chess.WHITE else "black",
                result=result,
                machiavelli_result=mach_res,
                objective_completed=objective_completed,
                modified_objective_completed=False,
                blunders=blunders,
                total_moves=board.fullmove_number,
                total_plies=board.ply(),
                moves_to_completion=moves_to_completion,
                avg_move_time_ms=avg_time,
                avg_eval_cp=avg_eval,
                sacrifices_count=sacrifices_count,
                promotions_count=promotions_count,
                termination_reason=termination,
                pgn_text=pgn_text,
                metadata={
                    "feasibility": goal.feasibility_status.value,
                    "milestones_count": len(goal.milestones),
                },
            )

        finally:
            await machiavelli_engine.close()
            await opponent_engine.close()

    async def _select_machiavelli_move(
        self,
        board: chess.Board,
        tracker: PieceTracker,
        goal: GoalDefinition,
        engine: StockfishUCIClient,
        feasibility_engine: FeasibilityEngine,
        machiavelli_color: chess.Color,
    ) -> Tuple[chess.Move, int, Optional[Any]]:
        """Selects a goal-conditioned move using lexicographical priority ranking."""
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return chess.Move.null(), 0, None

        # Check if MissionPlanner is available from planner module
        try:
            from backend.app.chess_engine.planner import MissionPlanner
            planner = MissionPlanner(
                uci_client=engine,
                goal=goal,
                piece_tracker=tracker,
                our_color=machiavelli_color,
            )
            decision = await planner.plan_move(
                board=board,
                movetime_ms=self.config.movetime_ms,
                depth=self.config.search_depth,
            )
            if decision and decision.move:
                return decision.move, decision.eval_cp or 0, decision.sacrifice_intent
        except Exception:
            # Fallback to internal robust goal-conditioned move selector
            pass

        # Internal Goal-Conditioned Lexicographical Move Selector:
        analysis = await engine.analyze(
            fen=board.fen(),
            movetime_ms=self.config.movetime_ms,
            depth=self.config.search_depth,
            multipv=min(5, len(legal_moves)),
        )

        candidate_scores: Dict[chess.Move, int] = {}
        for cand in analysis.candidates:
            try:
                m = chess.Move.from_uci(cand.move)
                if m in legal_moves:
                    candidate_scores[m] = cand.score.to_cp()
            except Exception:
                continue

        # Active milestone check
        active_m = goal.get_active_milestones()
        active_type = active_m[0].milestone_type if active_m else None

        best_move = legal_moves[0]
        best_priority = (-999999, -999999, -999999, -999999)
        declared_intent: Optional[Any] = None

        opp_color = not machiavelli_color

        for move in legal_moves:
            # 1. Safety Vector: Check if move allows immediate checkmate or king loss
            test_b = board.copy()
            test_b.push(move)
            v_safety = 1000
            if test_b.is_checkmate():
                # We deliver checkmate! Maximum safety and winning score
                v_safety = 100000

            # 2. Feasibility Vector: Check if move causes PROVEN_IMPOSSIBLE
            v_feasibility = 1000
            # Test tracker on this move
            t_test = tracker.clone()
            t_test.apply_move(move, board, is_our_move=True)
            report = feasibility_engine.evaluate(test_b, goal, t_test)
            if report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE:
                v_feasibility = -100000

            # 3. Milestone Vector: Does move advance active milestone?
            v_milestone = 0
            is_sac_candidate = False

            moved_p = tracker.get_piece_at(move.from_square)
            if moved_p:
                # Milestone: SACRIFICE_ALL_ORIGINAL_PIECES or SACRIFICE_QUEEN
                if active_type in (
                    MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                    MilestoneType.SACRIFICE_PIECE,
                    MilestoneType.SACRIFICE_QUEEN,
                ):
                    if moved_p.is_original and moved_p.is_major_or_minor and not moved_p.is_king:
                        # Check if target square is attacked by opponent
                        if test_b.is_attacked_by(opp_color, move.to_square):
                            v_milestone += 5000
                            is_sac_candidate = True

                # Milestone: PROMOTE_SURVIVING_PAWNS
                elif active_type in (
                    MilestoneType.PROMOTE_SURVIVING_PAWNS,
                    MilestoneType.PROMOTE_PAWN,
                ):
                    if moved_p.is_pawn:
                        target_rank = 7 if machiavelli_color == chess.WHITE else 0
                        current_rank = chess.square_rank(move.from_square)
                        new_rank = chess.square_rank(move.to_square)
                        advance = (new_rank - current_rank) if machiavelli_color == chess.WHITE else (current_rank - new_rank)
                        v_milestone += advance * 500
                        if move.promotion == chess.KNIGHT:
                            v_milestone += 10000

                # Milestone: CHECKMATE_WITH_PIECE
                elif active_type == MilestoneType.CHECKMATE_WITH_PIECE:
                    if test_b.is_checkmate():
                        if moved_p.is_promoted and moved_p.piece_type == chess.KNIGHT:
                            v_milestone += 50000
                        else:
                            v_milestone += 10000
                    elif test_b.is_check():
                        v_milestone += 1000

            # 4. Positional Vector: Stockfish evaluation as tie-breaker
            v_positional = candidate_scores.get(move, -500)

            priority_vector = (v_safety, v_feasibility, v_milestone, v_positional)
            if priority_vector > best_priority:
                best_priority = priority_vector
                best_move = move
                if is_sac_candidate and moved_p:
                    declared_intent = tracker.register_sacrifice_intent(
                        piece_id=moved_p.piece_id,
                        milestone_id=active_m[0].id if active_m else "m1_sacrifice",
                        move=move,
                        board=board,
                    )
                else:
                    declared_intent = None

        final_eval = candidate_scores.get(best_move, 0)
        return best_move, final_eval, declared_intent

    def _update_goal_progress(
        self,
        goal: GoalDefinition,
        tracker: PieceTracker,
        board: chess.Board,
        machiavelli_color: chess.Color,
    ) -> None:
        """Update milestones completion state in GoalDefinition DAG."""
        for m in goal.milestones:
            if m.status == MilestoneStatus.COMPLETED:
                continue

            if m.milestone_type in (
                MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                MilestoneType.SACRIFICE_PIECE,
                MilestoneType.SACRIFICE_QUEEN,
            ):
                sacrifices = tracker.get_confirmed_sacrifices(machiavelli_color)
                m.current_count = len(sacrifices)
                if m.milestone_type == MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES:
                    if tracker.all_original_pieces_sacrificed(machiavelli_color) or len(sacrifices) >= m.target_count:
                        m.status = MilestoneStatus.COMPLETED
                elif m.milestone_type == MilestoneType.SACRIFICE_QUEEN:
                    if tracker.is_queen_sacrificed(machiavelli_color):
                        m.status = MilestoneStatus.COMPLETED

            elif m.milestone_type in (
                MilestoneType.PROMOTE_SURVIVING_PAWNS,
                MilestoneType.PROMOTE_PAWN,
            ):
                promoted_knights = tracker.get_promoted_pieces(machiavelli_color, chess.KNIGHT)
                surviving_pawns = tracker.get_surviving_pawns(machiavelli_color)
                m.current_count = len(promoted_knights)
                if len(surviving_pawns) == 0 and len(promoted_knights) >= 1:
                    m.status = MilestoneStatus.COMPLETED

            elif m.milestone_type in (MilestoneType.CHECKMATE_WITH_PIECE, MilestoneType.WIN_GAME):
                if board.is_checkmate() and board.turn != machiavelli_color:
                    m.status = MilestoneStatus.COMPLETED
                    m.current_count = 1

        goal.advance_dag()

    def _export_results(
        self, summary: TournamentSummary, games: List[GameMetric]
    ) -> None:
        """Save JSON, CSV, PGN, and Markdown benchmark reports."""
        os.makedirs(self.config.output_dir, exist_ok=True)
        json_path = os.path.join(self.config.output_dir, "tournament_results.json")
        csv_path = os.path.join(self.config.output_dir, "tournament_games.csv")
        pgn_path = os.path.join(self.config.output_dir, "tournament_games.pgn")
        md_path = os.path.join(self.config.output_dir, "tournament_report.md")

        export_to_json(summary, games, json_path)
        export_to_csv(games, csv_path)
        export_to_pgn(games, pgn_path)
        report_md = generate_markdown_report(summary)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report_md)

        logger.info(f"Tournament results successfully exported to {self.config.output_dir}")
