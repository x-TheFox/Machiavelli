"""Machiavelli Mission Planner.

Coordinates:
1. Dynamic Milestone DAG progression: tracks milestone completion, advances DAG dependencies.
2. Proof-based Feasibility monitoring: checks invariants and impossibility proofs before search.
3. Hybrid Candidate Generation & Stockfish MultiPV integration.
4. Adversarial Search orchestration: drives search with Lexicographical GoalVector.
5. Decision Explanation Engine: generates plain-language, transparent rationales
   grounded in active milestones, tactical safety, and predicted lines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import chess

from backend.app.core.config import settings
from backend.app.chess_engine.board_manager import BoardManager
from backend.app.chess_engine.candidate_gen import (
    CandidateCategory,
    CandidateGenerator,
    TaggedCandidate,
)
from backend.app.chess_engine.feasibility import FeasibilityEngine
from backend.app.chess_engine.goal_evaluator import GoalEvaluator, GoalVector
from backend.app.chess_engine.goal_schema import (
    FeasibilityReport,
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import (
    PieceTracker,
    SacrificeIntent,
    TrackedPiece,
)
from backend.app.chess_engine.search import AdversarialSearch, SearchResult
from backend.app.chess_engine.uci_client import CandidateMove, StockfishUCIClient

logger = logging.getLogger(__name__)


@dataclass
class PlanResult:
    """The authoritative output of a Machiavelli planning turn."""
    move: chess.Move
    score: GoalVector
    explanation: Dict[str, Any]
    sacrifice_intent: Optional[SacrificeIntent] = None
    pv: List[chess.Move] = field(default_factory=list)
    depth_reached: int = 1
    active_milestone_id: Optional[str] = None
    feasibility_status: FeasibilityStatus = FeasibilityStatus.FEASIBLE
    search_nodes: int = 0
    time_ms: float = 0.0

    @property
    def uci(self) -> str:
        return self.move.uci()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "move": self.move.uci(),
            "score": self.score.as_dict(),
            "explanation": self.explanation,
            "sacrifice_intent": (
                {
                    "piece_id": self.sacrifice_intent.piece_id,
                    "target_square": chess.square_name(self.sacrifice_intent.target_square),
                    "milestone_id": self.sacrifice_intent.milestone_id,
                }
                if self.sacrifice_intent
                else None
            ),
            "pv": [m.uci() for m in self.pv],
            "depth_reached": self.depth_reached,
            "active_milestone_id": self.active_milestone_id,
            "feasibility_status": self.feasibility_status.value,
            "search_nodes": self.search_nodes,
            "time_ms": round(self.time_ms, 2),
        }


class MissionPlanner:
    """
    Authoritative mission planner driving Machiavelli's goal-conditioned chess execution.
    """

    def __init__(
        self,
        engine: Optional[StockfishUCIClient] = None,
        our_color: chess.Color = chess.WHITE,
        depth: int = 4,
    ):
        self.engine = engine
        self.our_color = our_color
        self.depth = depth

        self.feasibility_engine = FeasibilityEngine(our_color=our_color)
        self.candidate_gen = CandidateGenerator(our_color=our_color)
        self.search_engine = AdversarialSearch(our_color=our_color)
        self.evaluator = GoalEvaluator(our_color=our_color)

    async def select_move(
        self,
        board: Union[chess.Board, BoardManager, Any],
        goal: GoalDefinition,
        tracker: PieceTracker,
        candidates: Optional[List[CandidateMove]] = None,
        time_limit_ms: int = 2500,
    ) -> PlanResult:
        """
        Executes a complete planning turn:
        1. Advances and updates milestone DAG based on current state.
        2. Evaluates proof-based feasibility.
        3. Obtains or generates candidate moves (Stockfish MultiPV + goal moves).
        4. Runs iterative deepening adversarial minimax search.
        5. Formulates structured decision explanation.
        """
        # Resolve raw chess.Board safely
        actual_board = self._extract_board(board)

        # -------------------------------------------------------------
        # 1. Update and Advance Milestone DAG
        # -------------------------------------------------------------
        self.update_milestone_progress(actual_board, goal, tracker)
        active_m_id = goal.advance_dag()

        # -------------------------------------------------------------
        # 2. Check Feasibility
        # -------------------------------------------------------------
        feas_report = self.feasibility_engine.evaluate(actual_board, goal, tracker)
        goal.feasibility_status = feas_report.status
        goal.status_reason = feas_report.reason

        # -------------------------------------------------------------
        # 3. Retrieve Stockfish Candidates if Not Provided
        # -------------------------------------------------------------
        sf_candidates = candidates
        if sf_candidates is None and self.engine is not None and self.engine.is_running:
            try:
                analysis = await self.engine.analyze(
                    board_or_fen=actual_board,
                    multipv=settings.DEFAULT_MULTIPV,
                    depth=self.depth,
                    movetime_ms=min(1000, time_limit_ms // 2),
                )
                sf_candidates = analysis.candidates
            except Exception as e:
                logger.warning(f"Engine analysis failed: {e}. Proceeding with goal candidates.")
                sf_candidates = None

        # -------------------------------------------------------------
        # 4. Generate Hybrid Candidates
        # -------------------------------------------------------------
        tagged_candidates = self.candidate_gen.generate_candidates(
            board=actual_board,
            goal=goal,
            tracker=tracker,
            stockfish_candidates=sf_candidates,
            max_candidates=16,
        )

        # -------------------------------------------------------------
        # 5. Run Adversarial Minimax Search
        # -------------------------------------------------------------
        search_res = self.search_engine.search(
            board=actual_board,
            goal=goal,
            tracker=tracker,
            candidates=tagged_candidates,
            max_depth=self.depth,
            time_limit_ms=time_limit_ms,
        )

        selected_move = search_res.best_move
        selected_cand = search_res.tagged_candidate

        # -------------------------------------------------------------
        # 6. Extract Sacrifice Intent If Offered
        # -------------------------------------------------------------
        sacrifice_intent: Optional[SacrificeIntent] = None
        if selected_cand and selected_cand.sacrifice_intent:
            sacrifice_intent = selected_cand.sacrifice_intent
        else:
            # Check if this move constitutes a deliberate sacrifice offer
            piece_moved = actual_board.piece_at(selected_move.from_square)
            if piece_moved and piece_moved.piece_type != chess.KING:
                tracked_p = tracker.get_piece_at(selected_move.from_square)
                active_m = goal.get_milestone(goal.active_milestone_id or "") if goal.active_milestone_id else None
                if active_m and active_m.milestone_type in {
                    MilestoneType.SACRIFICE_PIECE,
                    MilestoneType.SACRIFICE_QUEEN,
                    MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
                }:
                    opp_color = not self.our_color
                    if actual_board.is_attacked_by(opp_color, selected_move.to_square):
                        if tracked_p and tracked_p.is_original:
                            sacrifice_intent = tracker.register_sacrifice_intent(
                                piece_id=tracked_p.piece_id,
                                milestone_id=active_m.id,
                                move=selected_move,
                                board=actual_board,
                            )

        # -------------------------------------------------------------
        # 7. Formulate Structured Decision Explanation
        # -------------------------------------------------------------
        explanation = self._formulate_explanation(
            actual_board, selected_move, selected_cand, search_res, goal, tracker, feas_report
        )

        return PlanResult(
            move=selected_move,
            score=search_res.score,
            explanation=explanation,
            sacrifice_intent=sacrifice_intent,
            pv=search_res.pv,
            depth_reached=search_res.depth_reached,
            active_milestone_id=goal.active_milestone_id,
            feasibility_status=feas_report.status,
            search_nodes=search_res.nodes_evaluated,
            time_ms=search_res.time_ms,
        )

    # -------------------------------------------------------------------------
    # Milestone DAG Management
    # -------------------------------------------------------------------------
    def update_milestone_progress(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
    ) -> None:
        """
        Detects milestone completion based on ground-truth piece tracker and board state.
        Transitions completed milestones from ACTIVE to COMPLETED.
        """
        active_milestones = goal.get_active_milestones()
        opp_color = not self.our_color

        for m in active_milestones:
            # 1. SACRIFICE_QUEEN
            if m.milestone_type == MilestoneType.SACRIFICE_QUEEN:
                if tracker.is_queen_sacrificed(self.our_color):
                    m.status = MilestoneStatus.COMPLETED
                    m.current_count = 1
                    logger.info(f"Milestone {m.id} (SACRIFICE_QUEEN) COMPLETED!")

            # 2. SACRIFICE_ALL_ORIGINAL_PIECES
            elif m.milestone_type == MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES:
                confirmed_sacs = tracker.get_confirmed_sacrifices(self.our_color)
                m.current_count = len(confirmed_sacs)
                if tracker.all_original_pieces_sacrificed(self.our_color):
                    m.status = MilestoneStatus.COMPLETED
                    logger.info(f"Milestone {m.id} (SACRIFICE_ALL_ORIGINAL_PIECES) COMPLETED!")

            # 3. SACRIFICE_PIECE
            elif m.milestone_type == MilestoneType.SACRIFICE_PIECE:
                confirmed_sacs = tracker.get_confirmed_sacrifices(self.our_color)
                m.current_count = len(confirmed_sacs)
                if m.current_count >= m.target_count:
                    m.status = MilestoneStatus.COMPLETED

            # 4. PROMOTE_SURVIVING_PAWNS
            elif m.milestone_type == MilestoneType.PROMOTE_SURVIVING_PAWNS:
                target_pt = chess.KNIGHT
                if m.target_piece_types and "queen" in m.target_piece_types[0].lower():
                    target_pt = chess.QUEEN

                promoted = tracker.get_promoted_pieces(self.our_color, target_pt)
                m.current_count = len(promoted)
                surviving = tracker.get_surviving_pawns(self.our_color)

                # Completed when all surviving pawns have been promoted (target_count reached)
                if m.target_count > 0 and m.current_count >= m.target_count:
                    m.status = MilestoneStatus.COMPLETED
                    logger.info(f"Milestone {m.id} (PROMOTE_SURVIVING_PAWNS) COMPLETED!")
                elif m.target_count == 0 and len(surviving) == 0 and m.current_count > 0:
                    m.status = MilestoneStatus.COMPLETED

            # 5. PROMOTE_ALL_8_PAWNS
            elif m.milestone_type == MilestoneType.PROMOTE_ALL_8_PAWNS:
                target_pt = chess.KNIGHT
                if m.target_piece_types and "queen" in m.target_piece_types[0].lower():
                    target_pt = chess.QUEEN
                promoted = tracker.get_promoted_pieces(self.our_color, target_pt)
                m.current_count = len(promoted)
                if m.current_count >= 8:
                    m.status = MilestoneStatus.COMPLETED

            # 6. CHECKMATE_WITH_PIECE
            elif m.milestone_type == MilestoneType.CHECKMATE_WITH_PIECE:
                if board.is_checkmate() and board.turn == opp_color:
                    req_promoted = m.conditions.get("require_promoted_lineage", False)
                    target_types = m.target_piece_types or ["knight"]

                    # Check which piece delivered checkmate (attacks opponent king)
                    opp_king = board.king(opp_color)
                    if opp_king is not None:
                        checkers = board.attackers(self.our_color, opp_king)
                        for sq in checkers:
                            tracked = tracker.get_piece_at(sq)
                            if tracked:
                                is_type_match = any(
                                    chess.piece_name(tracked.piece_type).lower() == t.lower()
                                    for t in target_types
                                )
                                if is_type_match:
                                    if req_promoted and not tracked.is_promoted:
                                        continue
                                    m.status = MilestoneStatus.COMPLETED
                                    m.current_count = 1
                                    logger.info(f"Milestone {m.id} (CHECKMATE_WITH_PIECE) COMPLETED!")
                                    break

            # 7. WIN_GAME
            elif m.milestone_type == MilestoneType.WIN_GAME:
                if board.is_checkmate() and board.turn == opp_color:
                    m.status = MilestoneStatus.COMPLETED
                    m.current_count = 1

    # -------------------------------------------------------------------------
    # Decision Explanation Engine
    # -------------------------------------------------------------------------
    def _formulate_explanation(
        self,
        board: chess.Board,
        move: chess.Move,
        cand: Optional[TaggedCandidate],
        search_res: SearchResult,
        goal: GoalDefinition,
        tracker: PieceTracker,
        feas_report: FeasibilityReport,
    ) -> Dict[str, Any]:
        """Generates a rich, structured plain-language rationale."""
        san = board.san(move) if move in board.legal_moves else move.uci()
        active_m = goal.get_milestone(goal.active_milestone_id or "") if goal.active_milestone_id else None
        active_title = active_m.title if active_m else "Tactical Play"

        # Determine primary strategic rationale
        categories = list(cand.categories) if cand else []
        intent_desc = "Conventional tactical continuation"

        if CandidateCategory.UNDERPROMOTION in categories:
            intent_desc = f"Promoting pawn to designated Knight ({san}) advancing milestone '{active_title}'"
        elif CandidateCategory.PROMOTION_ADVANCE in categories:
            to_rank = chess.square_rank(move.to_square)
            intent_desc = f"Advancing surviving pawn ({san}) toward promotion rank for '{active_title}'"
        elif CandidateCategory.SACRIFICE_OFFER in categories:
            piece_type_name = chess.piece_name(board.piece_at(move.from_square).piece_type)
            intent_desc = (
                f"Deliberate {piece_type_name} sacrifice ({san}) offered onto attacked square "
                f"to fulfill milestone '{active_title}'"
            )
        elif CandidateCategory.MATING_NET in categories:
            intent_desc = f"Maneuvering mating piece / delivering check ({san}) tightening king net"
        elif CandidateCategory.CLEARANCE in categories:
            intent_desc = f"Clearance move ({san}) opening path for advancing promotion pawns"
        elif CandidateCategory.KING_WALK in categories:
            intent_desc = f"King walk ({san}) escorting advancing pawns"

        # Safety evaluation summary
        safety_status = "Safe (no forced mate against us)"
        if search_res.score.safety <= -50000.0:
            safety_status = "CRITICAL: Forced mate threat detected!"
        elif search_res.score.safety >= 50000.0:
            safety_status = "Winning: Forced checkmate sequence identified"

        return {
            "rationale": intent_desc,
            "move_san": san,
            "active_milestone": active_title,
            "feasibility": feas_report.status.value,
            "safety_status": safety_status,
            "tactical_eval_cp": round(search_res.score.positional * 100.0, 1),
            "milestone_score": round(search_res.score.milestone, 1),
            "search_depth": search_res.depth_reached,
            "nodes_searched": search_res.nodes_evaluated,
            "pv_line": " ".join([m.uci() for m in search_res.pv[:5]]),
        }

    @staticmethod
    def _extract_board(board_or_bm: Any) -> chess.Board:
        """Safely extracts a python-chess Board from BoardManager or Board instance."""
        if hasattr(board_or_bm, "board"):
            attr = getattr(board_or_bm, "board")
            return attr() if callable(attr) else attr
        elif callable(board_or_bm):
            return board_or_bm()
        return board_or_bm
