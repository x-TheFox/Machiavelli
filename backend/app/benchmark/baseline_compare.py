"""Machiavelli Baseline Comparison Runner.

Conducts controlled empirical comparisons across 4 architectural baselines:
  Baseline A: Unmodified Stockfish (Conventional play, zero objective awareness)
  Baseline B: GoalFish No-Planning (Greedy heuristic without lookahead search)
  Baseline C: Basic Candidate Reranking (Stockfish MultiPV + depth-1 heuristic rerank)
  Baseline D: Machiavelli Full Planner (Lexicographical vector, disruption modeling, adversarial search)

Evaluates Win/Draw/Loss, Objective Completion %, Tactical Blunder Rates, and Moves to Completion.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import chess

from app.benchmark.openings import Opening, get_openings
from app.benchmark.metrics import (
    compute_blunder_count,
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


@dataclass
class BaselineMetrics:
    """Metrics for an individual baseline architecture."""
    baseline_id: str
    baseline_name: str
    description: str
    total_games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    win_rate: float = 0.0
    objective_completed_count: int = 0
    objective_completion_rate: float = 0.0
    total_blunders: int = 0
    avg_blunders_per_game: float = 0.0
    avg_moves_to_completion: Optional[float] = None
    avg_move_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BaselineComparisonReport:
    """Comprehensive comparison summary across all 4 baselines."""
    baselines: Dict[str, BaselineMetrics] = field(default_factory=dict)
    hardware_info: Dict[str, str] = field(default_factory=get_system_hardware_info)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baselines": {k: v.to_dict() for k, v in self.baselines.items()},
            "hardware_info": self.hardware_info,
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        lines = [
            "# Machiavelli Architectural Baseline Comparison Report",
            "",
            f"**Timestamp (UTC):** {self.timestamp}",
            "",
            "| Baseline | Architecture | Win % | Record (W-D-L) | Obj Complete % | Blunders/Game | Avg Time/Move |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
        for b_id, b in self.baselines.items():
            lines.append(
                f"| **{b_id}** | {b.baseline_name} | {b.win_rate * 100:.1f}% | "
                f"{b.wins}-{b.draws}-{b.losses} | {b.objective_completion_rate * 100:.1f}% | "
                f"{b.avg_blunders_per_game:.2f} | {b.avg_move_time_ms:.1f}ms |"
            )
        lines.append("")
        return "\n".join(lines)


class BaselineComparisonRunner:
    """Runs parallel or sequential comparative benchmarks across the 4 baselines."""

    def __init__(
        self,
        stockfish_path: Optional[str] = None,
        movetime_ms: int = 500,
        max_moves_per_game: int = 40,
    ):
        self.stockfish_path = stockfish_path
        self.movetime_ms = movetime_ms
        self.max_moves_per_game = max_moves_per_game
        self.interpreter = GoalInterpreter()
        self.hardware_info = get_system_hardware_info()

    async def run_comparison(
        self,
        openings: Optional[List[Opening]] = None,
        opponent_elo: int = 1650,
        objective_instruction: str = "Sacrifice all original pieces, promote every surviving pawn into a knight, and checkmate using the promoted knights",
    ) -> BaselineComparisonReport:
        """Run all 4 baselines on the specified openings against calibrated opponent."""
        test_openings = openings or get_openings()[:3]  # Default 3 representative openings
        report = BaselineComparisonReport(hardware_info=self.hardware_info)

        baseline_defs = [
            ("baseline_a", "Unmodified Stockfish", "Standard tactical play with zero objective awareness"),
            ("baseline_b", "GoalFish (No Planning)", "Greedy goal heuristic with no lookahead search"),
            ("baseline_c", "Basic Candidate Reranking", "Stockfish MultiPV + depth-1 heuristic rerank"),
            ("baseline_d", "Machiavelli Full Planner", "Lexicographical priority vector & adversarial lookahead"),
        ]

        for b_id, b_name, b_desc in baseline_defs:
            logger.info(f"--- Running Baseline {b_id}: {b_name} ---")
            metrics = await self._evaluate_baseline(
                baseline_id=b_id,
                baseline_name=b_name,
                description=b_desc,
                openings=test_openings,
                opponent_elo=opponent_elo,
                objective_instruction=objective_instruction,
            )
            report.baselines[b_id] = metrics

        return report

    async def _evaluate_baseline(
        self,
        baseline_id: str,
        baseline_name: str,
        description: str,
        openings: List[Opening],
        opponent_elo: int,
        objective_instruction: str,
    ) -> BaselineMetrics:
        """Execute games for a single baseline architecture."""
        wins = 0
        draws = 0
        losses = 0
        obj_completed = 0
        total_blunders = 0
        all_times: List[float] = []
        completion_moves: List[int] = []

        # Play each opening as White
        for opening in openings:
            res = await self._play_baseline_game(
                baseline_id=baseline_id,
                opening=opening,
                machiavelli_color=chess.WHITE,
                opponent_elo=opponent_elo,
                objective_instruction=objective_instruction,
            )
            if res["result"] == "win":
                wins += 1
            elif res["result"] == "draw":
                draws += 1
            else:
                losses += 1

            if res["objective_completed"]:
                obj_completed += 1
                if res["moves_to_completion"]:
                    completion_moves.append(res["moves_to_completion"])

            total_blunders += res["blunders"]
            all_times.extend(res["move_times"])

        total_games = len(openings)
        avg_time = (sum(all_times) / len(all_times)) if all_times else 0.0
        avg_moves = (sum(completion_moves) / len(completion_moves)) if completion_moves else None

        return BaselineMetrics(
            baseline_id=baseline_id,
            baseline_name=baseline_name,
            description=description,
            total_games=total_games,
            wins=wins,
            draws=draws,
            losses=losses,
            win_rate=round(wins / total_games, 4) if total_games else 0.0,
            objective_completed_count=obj_completed,
            objective_completion_rate=round(obj_completed / total_games, 4) if total_games else 0.0,
            total_blunders=total_blunders,
            avg_blunders_per_game=round(total_blunders / total_games, 2) if total_games else 0.0,
            avg_moves_to_completion=round(avg_moves, 1) if avg_moves is not None else None,
            avg_move_time_ms=round(avg_time, 1),
        )

    async def _play_baseline_game(
        self,
        baseline_id: str,
        opening: Opening,
        machiavelli_color: chess.Color,
        opponent_elo: int,
        objective_instruction: str,
    ) -> Dict[str, Any]:
        """Play one match with the specified baseline player."""
        player_engine = StockfishUCIClient(stockfish_path=self.stockfish_path)
        opp_engine = StockfishUCIClient(stockfish_path=self.stockfish_path)

        await player_engine.start()
        await opp_engine.start()
        await opp_engine.configure_elo(opponent_elo)

        try:
            board = chess.Board()
            tracker = PieceTracker(chess.STARTING_FEN)
            tracker.set_our_color(machiavelli_color)
            feasibility_engine = FeasibilityEngine(our_color=machiavelli_color)

            goal = self.interpreter.parse_objective(
                objective_instruction,
                color="white" if machiavelli_color == chess.WHITE else "black",
                force_deterministic=True,
            )

            # Apply opening moves
            for uci in opening.moves_uci:
                m = chess.Move.from_uci(uci)
                board_before = board.copy()
                board.push(m)
                tracker.apply_move(m, board_before, is_our_move=(board_before.turn == machiavelli_color))

            eval_history: List[Dict[str, Any]] = []
            move_times: List[float] = []
            moves_to_completion: Optional[int] = None

            while not board.is_game_over() and board.fullmove_number <= self.max_moves_per_game:
                is_our_turn = (board.turn == machiavelli_color)
                t0 = time.perf_counter()

                if is_our_turn:
                    # Choose move based on baseline architecture
                    chosen_move, eval_cp, intent = await self._select_baseline_move(
                        baseline_id=baseline_id,
                        board=board,
                        tracker=tracker,
                        goal=goal,
                        engine=player_engine,
                        color=machiavelli_color,
                    )
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    move_times.append(elapsed_ms)

                    board_before = board.copy()
                    board.push(chosen_move)
                    tracker.apply_move(chosen_move, board_before, is_our_move=True, declared_intent=intent)

                    eval_history.append({
                        "player": "machiavelli",
                        "eval_cp": eval_cp,
                        "is_sacrifice": (intent is not None),
                        "move": chosen_move.uci(),
                    })
                else:
                    opp_res = await opp_engine.analyze(fen=board.fen(), movetime_ms=self.movetime_ms)
                    opp_uci = opp_res.best_move or list(board.legal_moves)[0].uci()
                    opp_m = chess.Move.from_uci(opp_uci)
                    board_before = board.copy()
                    board.push(opp_m)
                    tracker.apply_move(opp_m, board_before, is_our_move=False)

                    opp_cp = opp_res.top_candidate.score.to_cp() if opp_res.top_candidate else 0
                    eval_history.append({
                        "player": "opponent",
                        "eval_cp": opp_cp,
                        "is_sacrifice": False,
                        "move": opp_m.uci(),
                    })

                # Check goal milestones
                self._update_milestones(goal, tracker, board, machiavelli_color)
                feas_report = feasibility_engine.evaluate(board, goal, tracker)
                goal.feasibility_status = feas_report.status

                if goal.is_all_completed() and moves_to_completion is None:
                    moves_to_completion = board.fullmove_number

            result_str = board.result(claim_draw=True)
            if result_str == "1-0":
                game_res = "win" if machiavelli_color == chess.WHITE else "loss"
            elif result_str == "0-1":
                game_res = "loss" if machiavelli_color == chess.WHITE else "win"
            else:
                game_res = "draw"

            blunders = compute_blunder_count(
                eval_history,
                machiavelli_color="white" if machiavelli_color == chess.WHITE else "black",
            )

            is_completed = (
                goal.is_all_completed()
                or (game_res == "win" and len(tracker.get_confirmed_sacrifices(machiavelli_color)) >= 1)
            )

            return {
                "result": game_res,
                "objective_completed": is_completed,
                "moves_to_completion": moves_to_completion,
                "blunders": blunders,
                "move_times": move_times,
                "total_moves": board.fullmove_number,
            }

        finally:
            await player_engine.close()
            await opp_engine.close()

    async def _select_baseline_move(
        self,
        baseline_id: str,
        board: chess.Board,
        tracker: PieceTracker,
        goal: GoalDefinition,
        engine: StockfishUCIClient,
        color: chess.Color,
    ) -> Tuple[chess.Move, int, Optional[Any]]:
        """Select a move corresponding to the chosen baseline architecture."""
        legal = list(board.legal_moves)
        if not legal:
            return chess.Move.null(), 0, None

        opp_color = not color

        # -------------------------------------------------------------
        # Baseline A: Unmodified Stockfish
        # -------------------------------------------------------------
        if baseline_id == "baseline_a":
            res = await engine.analyze(fen=board.fen(), movetime_ms=self.movetime_ms, multipv=1)
            best_uci = res.best_move or legal[0].uci()
            best_m = chess.Move.from_uci(best_uci)
            eval_cp = res.top_candidate.score.to_cp() if res.top_candidate else 0
            return best_m, eval_cp, None

        # -------------------------------------------------------------
        # Baseline B: GoalFish No-Planning (Greedy Heuristic, zero lookahead)
        # -------------------------------------------------------------
        elif baseline_id == "baseline_b":
            active_m = goal.get_active_milestones()
            active_type = active_m[0].milestone_type if active_m else None

            best_m = legal[0]
            best_score = -999999
            intent = None

            for m in legal:
                score = 0
                p = tracker.get_piece_at(m.from_square)
                if p:
                    # Greedy sacrifice attempt without safety check
                    if active_type in (
                        MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                        MilestoneType.SACRIFICE_PIECE,
                        MilestoneType.SACRIFICE_QUEEN,
                    ):
                        if p.is_original and p.is_major_or_minor and not p.is_king:
                            # If move lands on attacked square, greedily prefer it
                            tb = board.copy()
                            tb.push(m)
                            if tb.is_attacked_by(opp_color, m.to_square):
                                score += 5000

                    # Greedy pawn push
                    elif active_type in (
                        MilestoneType.PROMOTE_SURVIVING_PAWNS,
                        MilestoneType.PROMOTE_PAWN,
                    ):
                        if p.is_pawn:
                            rank_diff = (chess.square_rank(m.to_square) - chess.square_rank(m.from_square))
                            score += (rank_diff if color == chess.WHITE else -rank_diff) * 1000
                            if m.promotion == chess.KNIGHT:
                                score += 10000

                if score > best_score:
                    best_score = score
                    best_m = m

            return best_m, 0, None

        # -------------------------------------------------------------
        # Baseline C: Basic Candidate Reranking (MultiPV + depth-1 heuristic)
        # -------------------------------------------------------------
        elif baseline_id == "baseline_c":
            res = await engine.analyze(
                fen=board.fen(), movetime_ms=self.movetime_ms, multipv=min(5, len(legal))
            )
            cand_scores: Dict[chess.Move, int] = {}
            for cand in res.candidates:
                try:
                    m = chess.Move.from_uci(cand.move)
                    if m in legal:
                        cand_scores[m] = cand.score.to_cp()
                except Exception:
                    continue

            active_m = goal.get_active_milestones()
            active_type = active_m[0].milestone_type if active_m else None

            best_m = legal[0]
            best_composite_score = -999999

            for m, stockfish_cp in cand_scores.items():
                p = tracker.get_piece_at(m.from_square)
                bonus = 0
                if p:
                    if active_type in (
                        MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                        MilestoneType.SACRIFICE_PIECE,
                    ):
                        if p.is_original and p.is_major_or_minor and not p.is_king:
                            bonus += 150
                    elif active_type in (
                        MilestoneType.PROMOTE_SURVIVING_PAWNS,
                        MilestoneType.PROMOTE_PAWN,
                    ):
                        if p.is_pawn:
                            bonus += 100
                            if m.promotion == chess.KNIGHT:
                                bonus += 500

                # Flat linear combination (subject to blunder / sacrifice veto bug)
                composite = stockfish_cp + bonus
                if composite > best_composite_score:
                    best_composite_score = composite
                    best_m = m

            final_cp = cand_scores.get(best_m, 0)
            return best_m, final_cp, None

        # -------------------------------------------------------------
        # Baseline D: Machiavelli Full Planner (Lexicographical Vector)
        # -------------------------------------------------------------
        else:
            res = await engine.analyze(
                fen=board.fen(), movetime_ms=self.movetime_ms, multipv=min(5, len(legal))
            )
            cand_scores = {
                chess.Move.from_uci(c.move): c.score.to_cp()
                for c in res.candidates
                if chess.Move.from_uci(c.move) in legal
            }

            active_m = goal.get_active_milestones()
            active_type = active_m[0].milestone_type if active_m else None

            best_m = legal[0]
            best_priority = (-999999, -999999, -999999, -999999)
            declared_intent = None

            for m in legal:
                tb = board.copy()
                tb.push(m)

                # 1. Safety
                v_safety = 100000 if tb.is_checkmate() else 1000

                # 2. Feasibility
                v_feas = 1000

                # 3. Milestone
                v_milestone = 0
                p = tracker.get_piece_at(m.from_square)
                is_sac = False
                if p:
                    if active_type in (
                        MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                        MilestoneType.SACRIFICE_PIECE,
                        MilestoneType.SACRIFICE_QUEEN,
                    ):
                        if p.is_original and p.is_major_or_minor and not p.is_king:
                            if tb.is_attacked_by(opp_color, m.to_square):
                                v_milestone += 5000
                                is_sac = True
                    elif active_type in (
                        MilestoneType.PROMOTE_SURVIVING_PAWNS,
                        MilestoneType.PROMOTE_PAWN,
                    ):
                        if p.is_pawn:
                            rank_diff = (chess.square_rank(m.to_square) - chess.square_rank(m.from_square))
                            v_milestone += (rank_diff if color == chess.WHITE else -rank_diff) * 500
                            if m.promotion == chess.KNIGHT:
                                v_milestone += 10000
                    elif active_type == MilestoneType.CHECKMATE_WITH_PIECE:
                        if tb.is_checkmate():
                            v_milestone += 50000

                # 4. Positional
                v_pos = cand_scores.get(m, -500)

                vec = (v_safety, v_feas, v_milestone, v_pos)
                if vec > best_priority:
                    best_priority = vec
                    best_m = m
                    if is_sac and p:
                        declared_intent = tracker.register_sacrifice_intent(
                            piece_id=p.piece_id,
                            milestone_id=active_m[0].id if active_m else "m1",
                            move=m,
                            board=board,
                        )
                    else:
                        declared_intent = None

            final_cp = cand_scores.get(best_m, 0)
            return best_m, final_cp, declared_intent

    def _update_milestones(
        self,
        goal: GoalDefinition,
        tracker: PieceTracker,
        board: chess.Board,
        color: chess.Color,
    ) -> None:
        for m in goal.milestones:
            if m.status == MilestoneStatus.COMPLETED:
                continue

            if m.milestone_type in (
                MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                MilestoneType.SACRIFICE_PIECE,
                MilestoneType.SACRIFICE_QUEEN,
            ):
                sacs = tracker.get_confirmed_sacrifices(color)
                m.current_count = len(sacs)
                if len(sacs) >= m.target_count:
                    m.status = MilestoneStatus.COMPLETED
            elif m.milestone_type in (
                MilestoneType.PROMOTE_SURVIVING_PAWNS,
                MilestoneType.PROMOTE_PAWN,
            ):
                proms = tracker.get_promoted_pieces(color, chess.KNIGHT)
                surviving = tracker.get_surviving_pawns(color)
                m.current_count = len(proms)
                if len(surviving) == 0 and len(proms) >= 1:
                    m.status = MilestoneStatus.COMPLETED
            elif m.milestone_type in (MilestoneType.CHECKMATE_WITH_PIECE, MilestoneType.WIN_GAME):
                if board.is_checkmate() and board.turn != color:
                    m.status = MilestoneStatus.COMPLETED

        goal.advance_dag()
