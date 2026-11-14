"""Machiavelli Game Session & Authoritative Game Orchestrator.

Manages:
- Active python-chess board (BoardManager)
- Piece identity & sacrifice tracker (PieceTracker)
- Goal & milestone DAG (GoalDefinition, FeasibilityEngine, GoalInterpreter)
- Stockfish UCI process instance (StockfishUCIClient)
- Adversarial Search & Mission Planner (MissionPlanner)
- Dual-mode impossibility handler (Interactive vs Benchmark)
- Sequence-numbered event streaming and reconnection state recovery
- Multi-game concurrency isolation
"""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

import chess

from backend.app.chess_engine.board_manager import BoardManager, IllegalMoveError
from backend.app.chess_engine.uci_client import (
    StockfishUCIClient,
    AnalysisResult,
    CandidateMove,
    UCIScore,
)
from backend.app.chess_engine.goal_schema import (
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
    FeasibilityStatus,
    FeasibilityReport,
)
from backend.app.chess_engine.piece_tracker import (
    PieceTracker,
    TrackedPiece,
    SacrificeIntent,
    SacrificeEvent,
)
from backend.app.chess_engine.feasibility import FeasibilityEngine
from backend.app.chess_engine.goal_interpreter import GoalInterpreter
from backend.app.core.config import settings

# Optional import of planner and search if available
try:
    from backend.app.chess_engine.planner import MissionPlanner
except ImportError:
    try:
        from app.chess_engine.planner import MissionPlanner
    except ImportError:
        MissionPlanner = None

logger = logging.getLogger(__name__)


def compute_evidence_hash(data: Dict[str, Any]) -> str:
    """Generate deterministic SHA256 digest of impossibility evidence."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class GameSession:
    """Authoritative game session managing engine, board, planner, and real-time state."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        goal_text: str = "",
        mode: str = "interactive",  # "interactive" | "benchmark"
        machiavelli_color: chess.Color = chess.WHITE,
        opponent_type: str = "stockfish",  # "stockfish" | "human"
        opponent_elo: Optional[int] = 1950,
        start_fen: Optional[str] = None,
        stockfish_path: Optional[str] = None,
    ):
        self.session_id: str = session_id or str(uuid.uuid4())
        self.mode: str = mode.lower()
        self.machiavelli_color: chess.Color = machiavelli_color
        self.opponent_type: str = opponent_type.lower()
        self.opponent_elo: Optional[int] = opponent_elo
        self.start_fen: str = start_fen or chess.STARTING_FEN

        # Board and rules manager
        self.board: BoardManager = BoardManager(fen=self.start_fen)

        # Piece Tracker
        self.tracker: PieceTracker = PieceTracker(initial_fen=self.start_fen)
        self.tracker.set_our_color(self.machiavelli_color)

        # Feasibility Engine
        self.feasibility_engine: FeasibilityEngine = FeasibilityEngine(our_color=self.machiavelli_color)

        # Goal Definition & Interpreter
        self.goal_interpreter: GoalInterpreter = GoalInterpreter()
        self.raw_goal_text: str = goal_text
        self.goal: GoalDefinition = self._initialize_goal(goal_text)

        # Stockfish UCI Client for Machiavelli
        self.engine_path: str = stockfish_path or settings.STOCKFISH_PATH
        self.engine: StockfishUCIClient = StockfishUCIClient(
            stockfish_path=self.engine_path,
            threads=settings.STOCKFISH_THREADS,
            hash_size_mb=settings.STOCKFISH_HASH,
        )

        # Opponent Stockfish client (if playing against calibrated engine)
        self.opponent_engine: Optional[StockfishUCIClient] = None
        if self.opponent_type == "stockfish":
            self.opponent_engine = StockfishUCIClient(
                stockfish_path=self.engine_path,
                threads=1,
                hash_size_mb=32,
            )

        # Mission Planner instance
        self.planner: Any = None
        if MissionPlanner is not None:
            try:
                self.planner = MissionPlanner(
                    engine=self.engine,
                    our_color=self.machiavelli_color,
                    depth=settings.DEFAULT_SEARCH_DEPTH,
                )
            except Exception as e:
                logger.warning(f"Failed to initialize MissionPlanner: {e}. Falling back to default search.")

        # Game state tracking
        self.status: str = "active"  # "active", "completed", "impossible", "resigned", "draw", "paused"
        self.is_paused: bool = False
        self.pending_fallback: bool = False
        self.fallback_prompt_data: Optional[Dict[str, Any]] = None
        self.fallback_to_conventional: bool = False
        self.relaxed_constraints_count: int = 0
        self.objective_completed: bool = False
        self.objective_failed: bool = False
        self.impossibility_evidence: Optional[str] = None
        self.result: Optional[str] = None
        self.termination_reason: Optional[str] = None

        # Last analysis snapshots
        self.last_analysis: Optional[AnalysisResult] = None
        self.last_candidate_moves: List[Dict[str, Any]] = []
        self.last_explanation: Optional[Dict[str, Any]] = None

        # Move execution & concurrency mutex
        self.lock: asyncio.Lock = asyncio.Lock()
        self.is_thinking: bool = False
        self.created_at: datetime = datetime.now(timezone.utc)
        self.updated_at: datetime = datetime.now(timezone.utc)

        # Event stream & Reconnection log
        self.seq: int = 0
        self.event_history: List[Dict[str, Any]] = []
        self.max_event_history: int = 1000
        self._listeners: Set[Callable[[Dict[str, Any]], Any]] = set()

    def _initialize_goal(self, goal_text: str) -> GoalDefinition:
        """Parse or generate initial GoalDefinition from goal text."""
        color_name = "white" if self.machiavelli_color == chess.WHITE else "black"
        if not goal_text.strip():
            # Default empty / standard win goal
            return GoalDefinition(
                goal_id=f"goal_{self.session_id[:8]}",
                raw_instruction="Win the game",
                color=color_name,
                title="Conventional Victory",
                description="Play standard chess and deliver checkmate",
                milestones=[
                    Milestone(
                        id="win_game",
                        title="Checkmate Opponent",
                        description="Deliver checkmate against the opposing king",
                        milestone_type=MilestoneType.WIN_GAME,
                        status=MilestoneStatus.ACTIVE,
                    )
                ],
                active_milestone_id="win_game",
                feasibility_status=FeasibilityStatus.FEASIBLE,
            )

        try:
            return self.goal_interpreter.parse_objective(goal_text, color=color_name)
        except Exception as e:
            logger.error(f"Error parsing goal '{goal_text}': {e}. Using fallback goal.")
            return GoalDefinition(
                goal_id=f"goal_{self.session_id[:8]}",
                raw_instruction=goal_text,
                color=color_name,
                title="Custom Objective",
                description=goal_text,
                milestones=[
                    Milestone(
                        id="custom_objective",
                        title="Complete Objective",
                        description=goal_text,
                        milestone_type=MilestoneType.CUSTOM,
                        status=MilestoneStatus.ACTIVE,
                    )
                ],
                active_milestone_id="custom_objective",
                feasibility_status=FeasibilityStatus.FEASIBLE,
            )

    async def initialize(self) -> None:
        """Start underlying UCI engine processes and set initial options."""
        async with self.lock:
            await self.engine.start()
            if self.opponent_engine:
                await self.opponent_engine.start()
                if self.opponent_elo:
                    await self.opponent_engine.configure_elo(self.opponent_elo)

            # Record initial state event
            await self._record_and_broadcast_state()

    async def close(self) -> None:
        """Shut down engine subprocesses and release resources."""
        async with self.lock:
            try:
                await self.engine.close()
            except Exception as e:
                logger.warning(f"Error quitting Machiavelli engine: {e}")
            if self.opponent_engine:
                try:
                    await self.opponent_engine.close()
                except Exception as e:
                    logger.warning(f"Error quitting Opponent engine: {e}")

    # --------------------------------------------------------------------------
    # Event Emission & State Recovery
    # --------------------------------------------------------------------------

    def add_listener(self, listener: Callable[[Dict[str, Any]], Any]) -> None:
        """Register a callback or WebSocket sender for session events."""
        self._listeners.add(listener)

    def remove_listener(self, listener: Callable[[Dict[str, Any]], Any]) -> None:
        """Deregister an event listener."""
        self._listeners.discard(listener)

    async def broadcast_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Record an event with monotonic sequence number and dispatch to listeners."""
        self.seq += 1
        self.updated_at = datetime.now(timezone.utc)
        envelope = {
            "seq": self.seq,
            "session_id": self.session_id,
            "type": event_type,
            "timestamp": self.updated_at.isoformat(),
            "payload": payload,
        }
        self.event_history.append(envelope)
        if len(self.event_history) > self.max_event_history:
            self.event_history.pop(0)

        for listener in list(self._listeners):
            try:
                res = listener(envelope)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.debug(f"Listener error during broadcast: {e}")

        return envelope

    def get_events_since(self, last_seq: int) -> List[Dict[str, Any]]:
        """Return all missed events with seq > last_seq for client reconnection."""
        return [ev for ev in self.event_history if ev["seq"] > last_seq]

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Generate authoritative full state snapshot for client synchronization."""
        turn_str = "white" if self.board.turn == chess.WHITE else "black"
        surviving_pawns = len(self.tracker.get_surviving_pawns(self.machiavelli_color))
        confirmed_sacrifices = len(self.tracker.get_confirmed_sacrifices(self.machiavelli_color))
        promoted_knights = len(self.tracker.get_promoted_pieces(self.machiavelli_color, chess.KNIGHT))

        return {
            "session_id": self.session_id,
            "current_seq": self.seq,
            "mode": self.mode,
            "status": self.status,
            "is_paused": self.is_paused,
            "pending_fallback": self.pending_fallback,
            "fallback_prompt": self.fallback_prompt_data,
            "fallback_to_conventional": self.fallback_to_conventional,
            "machiavelli_color": "white" if self.machiavelli_color == chess.WHITE else "black",
            "opponent_type": self.opponent_type,
            "opponent_elo": self.opponent_elo,
            "fen": self.board.fen,
            "start_fen": self.start_fen,
            "turn": turn_str,
            "ply": self.board.ply,
            "fullmove_number": self.board.fullmove_number,
            "is_check": self.board.is_check(),
            "is_game_over": self.board.is_game_over(),
            "result": self.result or self.board.result(),
            "termination_reason": self.termination_reason or self.board.termination_reason(),
            "move_history_san": self.board.san_history(),
            "move_history_uci": self.board.uci_history(),
            "objective_completed": self.objective_completed,
            "objective_failed": self.objective_failed,
            "impossibility_evidence": self.impossibility_evidence,
            "goal": {
                "id": self.goal.goal_id,
                "title": self.goal.title,
                "description": self.goal.description,
                "raw_instruction": self.goal.raw_instruction,
                "feasibility_status": self.goal.feasibility_status.value,
                "status_reason": self.goal.status_reason,
                "active_milestone_id": self.goal.active_milestone_id,
                "milestones": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "description": m.description,
                        "type": m.milestone_type.value,
                        "status": m.status.value,
                        "target_count": m.target_count,
                        "current_count": m.current_count,
                        "progress": m.progress_ratio,
                        "dependencies": m.dependencies,
                    }
                    for m in self.goal.milestones
                ],
            },
            "piece_metrics": {
                "surviving_pawns": surviving_pawns,
                "confirmed_sacrifices": confirmed_sacrifices,
                "promoted_knights": promoted_knights,
            },
            "last_candidate_moves": self.last_candidate_moves,
            "last_explanation": self.last_explanation,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    # --------------------------------------------------------------------------
    # Board State & Feasibility Updates
    # --------------------------------------------------------------------------

    async def _record_and_broadcast_state(
        self,
        last_move: Optional[chess.Move] = None,
        last_san: Optional[str] = None,
    ) -> None:
        """Broadcast BOARD_STATE, FEASIBILITY_CHANGE, and MILESTONE_UPDATE events."""
        turn_str = "white" if self.board.turn == chess.WHITE else "black"
        surviving_pawns = len(self.tracker.get_surviving_pawns(self.machiavelli_color))
        confirmed_sacrifices = len(self.tracker.get_confirmed_sacrifices(self.machiavelli_color))
        promoted_knights = len(self.tracker.get_promoted_pieces(self.machiavelli_color, chess.KNIGHT))

        # Check game over conditions
        is_over = self.board.is_game_over()
        if is_over and not self.result:
            self.result = self.board.result()
            self.termination_reason = self.board.termination_reason()
            self.status = "completed"

        # Evaluate feasibility
        report = self.feasibility_engine.evaluate(
            board=self.board.board,
            goal=self.goal,
            tracker=self.tracker,
        )
        self.goal.feasibility_status = report.status
        self.goal.status_reason = report.reason

        # Broadcast BOARD_STATE
        await self.broadcast_event(
            "BOARD_STATE",
            {
                "fen": self.board.fen,
                "uci": last_move.uci() if last_move else None,
                "san": last_san,
                "turn": turn_str,
                "ply": self.board.ply,
                "fullmove_number": self.board.fullmove_number,
                "is_check": self.board.is_check(),
                "is_game_over": is_over,
                "result": self.result,
                "termination_reason": self.termination_reason,
                "surviving_pawns_count": surviving_pawns,
                "sacrificed_pieces_count": confirmed_sacrifices,
                "promoted_knights_count": promoted_knights,
            },
        )

        # Broadcast FEASIBILITY_CHANGE
        await self.broadcast_event(
            "FEASIBILITY_CHANGE",
            {
                "status": report.status.value,
                "reason": report.reason,
                "broken_invariant_id": report.broken_invariant_id,
                "failed_milestone_id": report.failed_milestone_id,
                "threatened_entities": report.threatened_entities,
                "evidence": report.evidence,
            },
        )

        # Check DAG advancement
        self.goal.advance_dag()

        # Broadcast MILESTONE_UPDATE
        await self.broadcast_event(
            "MILESTONE_UPDATE",
            {
                "active_milestone_id": self.goal.active_milestone_id,
                "all_completed": self.goal.is_all_completed(),
                "milestones": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "description": m.description,
                        "status": m.status.value,
                        "current_count": m.current_count,
                        "target_count": m.target_count,
                        "progress": m.progress_ratio,
                    }
                    for m in self.goal.milestones
                ],
            },
        )

        # Handle impossibility trigger if PROVEN_IMPOSSIBLE
        if report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE:
            await self._handle_impossibility(report)

        # If game is over, broadcast GAME_OVER
        if is_over:
            await self._handle_game_over()

    # --------------------------------------------------------------------------
    # Impossibility Handler (Dual-Mode)
    # --------------------------------------------------------------------------

    async def _handle_impossibility(self, report: FeasibilityReport) -> None:
        """
        Handle mathematical proof of impossibility in accordance with session mode:
        - Interactive Mode: Prompt user with 3 options and await response.
        - Benchmark Mode: Record cryptographic proof, lock metadata, and fall back to Stockfish.
        """
        if self.objective_failed or self.fallback_to_conventional:
            return  # Already handled

        evidence_payload = {
            "session_id": self.session_id,
            "ply": self.board.ply,
            "fen": self.board.fen,
            "reason": report.reason,
            "broken_invariant_id": report.broken_invariant_id,
            "failed_milestone_id": report.failed_milestone_id,
            "evidence": report.evidence,
            "move_history": self.board.san_history(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        crypto_hash = compute_evidence_hash(evidence_payload)
        evidence_payload["sha256_hash"] = crypto_hash
        self.impossibility_evidence = json.dumps(evidence_payload)

        if self.mode == "benchmark":
            logger.info(
                f"[Session {self.session_id}] Benchmark Mode: Objective impossibility proven: {report.reason}. "
                f"Hash: {crypto_hash}. Falling back to conventional Stockfish."
            )
            self.objective_failed = True
            self.objective_completed = False
            self.fallback_to_conventional = True
            self.status = "impossible"

            # Emit fallback notice
            await self.broadcast_event(
                "FALLBACK_NOTICE",
                {
                    "mode": "benchmark",
                    "reason": report.reason,
                    "evidence_hash": crypto_hash,
                    "action": "conventional_fallback",
                },
            )

        else:
            # Interactive Mode: pause and prompt user
            logger.info(
                f"[Session {self.session_id}] Interactive Mode: Objective impossibility proven: {report.reason}. "
                "Emitting FALLBACK_PROMPT."
            )
            self.pending_fallback = True
            self.is_paused = True
            self.fallback_prompt_data = {
                "reason": report.reason,
                "broken_invariant_id": report.broken_invariant_id,
                "failed_milestone_id": report.failed_milestone_id,
                "evidence_hash": crypto_hash,
                "choices": [
                    {
                        "id": "relax_constraint",
                        "label": "Relax Constraint",
                        "description": "Relax the broken invariant to the nearest feasible variant and continue",
                    },
                    {
                        "id": "conventional_win",
                        "label": "Revert to Conventional Win",
                        "description": "Switch Machiavelli to standard Stockfish play to secure victory",
                    },
                    {
                        "id": "resign",
                        "label": "Resign Game",
                        "description": "Acknowledge defeat and terminate the game session",
                    },
                ],
            }

            await self.broadcast_event("FALLBACK_PROMPT", self.fallback_prompt_data)

    async def handle_fallback_choice(self, choice: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Apply user selection for the dual-mode impossibility prompt."""
        async with self.lock:
            if not self.pending_fallback:
                return {"status": "error", "message": "No pending fallback prompt"}

            choice = choice.lower().strip()
            self.pending_fallback = False
            self.fallback_prompt_data = None

            if choice == "relax_constraint":
                self.relaxed_constraints_count += 1
                self.goal.feasibility_status = FeasibilityStatus.FEASIBLE
                self.goal.status_reason = f"Constraint relaxed by user (relaxation #{self.relaxed_constraints_count})"

                # Mark active milestone as relaxed or activate next
                if self.goal.active_milestone_id:
                    active_m = self.goal.get_milestone(self.goal.active_milestone_id)
                    if active_m:
                        active_m.status = MilestoneStatus.COMPLETED
                self.goal.advance_dag()

                self.is_paused = False
                logger.info(f"[Session {self.session_id}] User chose: Relax Constraint")
                await self.broadcast_event(
                    "FALLBACK_RESOLVED",
                    {"choice": "relax_constraint", "relaxed_count": self.relaxed_constraints_count},
                )

            elif choice == "conventional_win":
                self.fallback_to_conventional = True
                self.objective_failed = True
                self.is_paused = False
                logger.info(f"[Session {self.session_id}] User chose: Revert to Conventional Win")
                await self.broadcast_event(
                    "FALLBACK_RESOLVED",
                    {"choice": "conventional_win", "action": "playing_stockfish"},
                )

            elif choice == "resign":
                self.status = "resigned"
                self.result = "0-1" if self.machiavelli_color == chess.WHITE else "1-0"
                self.termination_reason = "Machiavelli resigned due to objective impossibility"
                self.objective_failed = True
                self.is_paused = False
                logger.info(f"[Session {self.session_id}] User chose: Resign")
                await self.broadcast_event(
                    "FALLBACK_RESOLVED",
                    {"choice": "resign", "result": self.result},
                )
                await self._handle_game_over()

            else:
                self.pending_fallback = True
                return {"status": "error", "message": f"Unknown choice: {choice}"}

            return {"status": "ok", "choice": choice}

    # --------------------------------------------------------------------------
    # Game Over Handling
    # --------------------------------------------------------------------------

    async def _handle_game_over(self) -> None:
        """Finalize game over state, compute objective success, and broadcast GAME_OVER."""
        if not self.result:
            self.result = self.board.result()
        if not self.termination_reason:
            self.termination_reason = self.board.termination_reason()

        # Check if objective completed: all milestones reached + game won (if win required)
        won_game = (
            (self.result == "1-0" and self.machiavelli_color == chess.WHITE)
            or (self.result == "0-1" and self.machiavelli_color == chess.BLACK)
        )
        if self.goal.is_all_completed() and (won_game or not self.goal.get_milestone("win_game")):
            self.objective_completed = True
            self.status = "completed"
        else:
            self.status = "completed" if won_game else ("resigned" if self.status == "resigned" else "failed")

        payload = {
            "result": self.result,
            "reason": self.termination_reason,
            "objective_completed": self.objective_completed,
            "objective_failed": self.objective_failed,
            "fallback_used": self.fallback_to_conventional or self.relaxed_constraints_count > 0,
            "total_plies": self.board.ply,
            "pgn": self._build_pgn(),
            "fen": self.board.fen,
        }
        await self.broadcast_event("GAME_OVER", payload)

    def _build_pgn(self) -> str:
        """Construct standard PGN representation of the played game."""
        game = chess.pgn.Game()
        game.headers["Event"] = "Machiavelli Autonomous Match"
        game.headers["Site"] = "Machiavelli Engine"
        game.headers["Date"] = self.created_at.strftime("%Y.%m.%d")
        game.headers["Round"] = "1"
        game.headers["White"] = "Machiavelli" if self.machiavelli_color == chess.WHITE else f"Opponent ({self.opponent_elo or 'Custom'})"
        game.headers["Black"] = f"Opponent ({self.opponent_elo or 'Custom'})" if self.machiavelli_color == chess.WHITE else "Machiavelli"
        game.headers["Result"] = self.result or "*"
        if self.start_fen != chess.STARTING_FEN:
            game.headers["SetUp"] = "1"
            game.headers["FEN"] = self.start_fen

        node = game
        tmp_board = chess.Board(self.start_fen)
        for uci_str in self.board.uci_history():
            move = chess.Move.from_uci(uci_str)
            node = node.add_variation(move)
            tmp_board.push(move)

        return str(game)

    # --------------------------------------------------------------------------
    # Move Execution (Human, Machiavelli, Opponent Engine)
    # --------------------------------------------------------------------------

    async def execute_player_move(self, move_str: str) -> Dict[str, Any]:
        """Execute a move supplied by the user / external player."""
        async with self.lock:
            if self.board.is_game_over() or self.status in {"completed", "resigned"}:
                return {"status": "error", "message": "Game is already over"}
            if self.is_paused or self.pending_fallback:
                return {"status": "error", "message": "Game is paused pending fallback choice"}

            try:
                move = self.board.parse_move(move_str)
            except IllegalMoveError as e:
                return {"status": "error", "message": f"Illegal move: {e}"}

            board_before = self.board.board.copy()
            move_san = board_before.san(move)
            is_our_move = (board_before.turn == self.machiavelli_color)
            self.board.push(move)
            self.tracker.apply_move(move, board_before, is_our_move=is_our_move)

            await self._record_and_broadcast_state(last_move=move, last_san=move_san)
            return {"status": "ok", "move": move.uci(), "san": move_san, "fen": self.board.fen}

    async def step_turn(self) -> Dict[str, Any]:
        """
        Advance one turn automatically:
        If it's Machiavelli's turn, select and execute Machiavelli move.
        If it's Opponent's turn and opponent_type is 'stockfish', execute opponent move.
        """
        async with self.lock:
            if self.board.is_game_over() or self.status in {"completed", "resigned"}:
                return {"status": "game_over", "result": self.result}
            if self.is_paused or self.pending_fallback:
                return {"status": "paused", "message": "Waiting for fallback choice"}
            if self.is_thinking:
                return {"status": "busy", "message": "Engine is currently computing"}

            self.is_thinking = True

        try:
            current_turn = self.board.turn
            if current_turn == self.machiavelli_color:
                return await self._execute_machiavelli_turn()
            else:
                if self.opponent_type == "stockfish":
                    return await self._execute_opponent_turn()
                else:
                    return {"status": "waiting_player", "turn": "opponent"}
        finally:
            async with self.lock:
                self.is_thinking = False

    async def _execute_machiavelli_turn(self) -> Dict[str, Any]:
        """Compute and execute Machiavelli's move using planner or Stockfish fallback."""
        fen = self.board.fen
        moves_history = self.board.uci_history()

        # 1. Run Stockfish MultiPV analysis for candidate baseline & evaluation
        analysis: AnalysisResult = await self.engine.analyze(
            fen=fen,
            multipv=settings.DEFAULT_MULTIPV,
            depth=settings.DEFAULT_SEARCH_DEPTH,
            movetime_ms=settings.DEFAULT_SEARCH_MOVETIME_MS,
        )
        self.last_analysis = analysis

        # Broadcast STOCKFISH_EVAL
        top_cand = analysis.top_candidate
        top_score = top_cand.score if top_cand else UCIScore()
        eval_depth = analysis.depth_reached or (top_cand.depth if top_cand else 0)
        eval_nodes = analysis.nodes_evaluated or (top_cand.nodes if top_cand else 0)
        eval_nps = top_cand.nps if top_cand else 0
        best_move_str = analysis.best_move or (top_cand.move if top_cand else None)

        await self.broadcast_event(
            "STOCKFISH_EVAL",
            {
                "cp": top_score.cp,
                "mate": top_score.mate,
                "depth": eval_depth,
                "nodes": eval_nodes,
                "nps": eval_nps,
                "best_move": best_move_str,
            },
        )

        # Broadcast CANDIDATE_MOVES
        candidates_data = [
            {
                "multipv": c.multipv,
                "uci": c.move,
                "san": self.board.uci_to_san(c.move) if self.board.is_legal(c.move) else c.move,
                "cp": c.score.cp,
                "mate": c.score.mate,
                "pv": c.pv,
            }
            for c in analysis.candidates
        ]
        self.last_candidate_moves = candidates_data
        await self.broadcast_event("CANDIDATE_MOVES", {"candidates": candidates_data})

        # 2. Select move: use MissionPlanner if available and not in conventional fallback
        selected_move_str: Optional[str] = None
        decision_explanation: Dict[str, Any] = {}
        sacrifice_intent: Optional[SacrificeIntent] = None

        if self.planner is not None and not self.fallback_to_conventional:
            try:
                plan_result = await self.planner.select_move(
                    board=self.board.board,
                    goal=self.goal,
                    tracker=self.tracker,
                    candidates=analysis.candidates,
                )
                if plan_result and hasattr(plan_result, "move"):
                    selected_move_str = plan_result.move.uci()
                    decision_explanation = getattr(plan_result, "explanation", {})
                    sacrifice_intent = getattr(plan_result, "sacrifice_intent", None)
            except Exception as e:
                logger.warning(f"Planner error: {e}. Falling back to top Stockfish candidate.")

        if not selected_move_str:
            # Fallback to Stockfish's top move
            selected_move_str = best_move_str
            if not selected_move_str:
                legal = self.board.legal_moves_uci
                if legal:
                    selected_move_str = legal[0]
                else:
                    return {"status": "game_over", "result": self.board.result()}
            decision_explanation = {
                "rationale": "Tactical Stockfish continuation",
                "milestone": self.goal.active_milestone_id or "conventional_play",
                "safety": "Engine verified",
            }

        # 4. Push move to board & update piece tracker
        move = chess.Move.from_uci(selected_move_str)
        board_before = self.board.board.copy()
        move_san = board_before.san(move)

        self.board.push(move)
        self.tracker.apply_move(move, board_before, is_our_move=True, declared_intent=sacrifice_intent)

        # 5. Broadcast EXPLANATION
        self.last_explanation = {
            "ply": self.board.ply,
            "move_uci": selected_move_str,
            "move_san": move_san,
            "explanation": decision_explanation,
            "is_sacrifice": sacrifice_intent is not None,
        }
        await self.broadcast_event("EXPLANATION", self.last_explanation)

        # 6. Record and broadcast new state
        await self._record_and_broadcast_state(last_move=move, last_san=move_san)

        return {
            "status": "ok",
            "player": "machiavelli",
            "move": selected_move_str,
            "san": move_san,
            "fen": self.board.fen,
        }

    async def _execute_opponent_turn(self) -> Dict[str, Any]:
        """Compute and execute Opponent's move via opponent Stockfish client."""
        if not self.opponent_engine:
            return {"status": "error", "message": "Opponent engine not initialized"}

        fen = self.board.fen
        analysis = await self.opponent_engine.analyze(
            fen=fen,
            multipv=1,
            depth=settings.DEFAULT_SEARCH_DEPTH,
            movetime_ms=min(settings.DEFAULT_SEARCH_MOVETIME_MS, 1500),
        )
        move_uci = analysis.best_move()
        if not move_uci:
            legal = self.board.legal_moves_uci
            if legal:
                move_uci = legal[0]
            else:
                return {"status": "game_over", "result": self.board.result()}

        move = chess.Move.from_uci(move_uci)
        board_before = self.board.board.copy()
        move_san = board_before.san(move)

        self.board.push(move)
        self.tracker.apply_move(move, board_before, is_our_move=False)

        await self._record_and_broadcast_state(last_move=move, last_san=move_san)

        return {
            "status": "ok",
            "player": "opponent",
            "move": move_uci,
            "san": move_san,
            "fen": self.board.fen,
        }


# --------------------------------------------------------------------------
# Multi-Session Registry & Concurrency Manager
# --------------------------------------------------------------------------

class SessionManager:
    """Singleton registry managing active GameSession instances concurrently."""

    _instance: Optional["SessionManager"] = None

    def __new__(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions = {}
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def create_session(
        self,
        goal_text: str = "",
        mode: str = "interactive",
        machiavelli_color: chess.Color = chess.WHITE,
        opponent_type: str = "stockfish",
        opponent_elo: Optional[int] = 1950,
        start_fen: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> GameSession:
        """Create and initialize a new independent game session."""
        async with self._lock:
            session = GameSession(
                session_id=session_id,
                goal_text=goal_text,
                mode=mode,
                machiavelli_color=machiavelli_color,
                opponent_type=opponent_type,
                opponent_elo=opponent_elo,
                start_fen=start_fen,
            )
            await session.initialize()
            self._sessions[session.session_id] = session
            logger.info(f"Created game session {session.session_id} (mode={mode})")
            return session

    async def get_session(self, session_id: str) -> Optional[GameSession]:
        """Retrieve active game session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """Shut down and remove game session from registry."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                await session.close()
                logger.info(f"Closed and removed game session {session_id}")
                return True
            return False

    async def list_active_sessions(self) -> List[Dict[str, Any]]:
        """List summary of all active sessions."""
        async with self._lock:
            return [
                {
                    "session_id": sid,
                    "mode": s.mode,
                    "status": s.status,
                    "ply": s.board.ply,
                    "fen": s.board.fen,
                    "created_at": s.created_at.isoformat(),
                }
                for sid, s in self._sessions.items()
            ]


session_manager = SessionManager()
