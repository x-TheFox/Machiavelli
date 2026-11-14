"""Machiavelli Lexicographical Goal Evaluator.

Implements the priority-ordered evaluation vector:
    V(s) = <V_safety, V_feasibility, V_milestone, V_positional>

Design Principles:
1. Strictly Lexicographical: Comparisons prioritize Safety first, then Feasibility,
   then Milestone progress, and finally Positional/Stockfish tactical compensation.
2. NO UNIVERSAL -600cp FILTER: Conventional evaluation penalties do not automatically
   eliminate objective-critical sacrifices. Forced-mate avoidance and lexicographical
   priority dictate survival.
3. Proof-Grounded: Integrates directly with FeasibilityEngine, PieceTracker, and
   GoalDefinition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import chess

from backend.app.chess_engine.goal_schema import (
    FeasibilityReport,
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import (
    PIECE_VALUES,
    PieceTracker,
    TrackedPiece,
)
from backend.app.chess_engine.feasibility import FeasibilityEngine
from backend.app.chess_engine.uci_client import UCIScore


@dataclass(frozen=True)
class GoalVector:
    """
    Lexicographical evaluation vector V(s) = <safety, feasibility, milestone, positional>.
    Python tuple comparison gives the exact lexicographical ordering:
    A > B iff (A.safety > B.safety) or
              (A.safety == B.safety and A.feasibility > B.feasibility) or ...
    """
    safety: float = 0.0
    feasibility: float = 0.0
    milestone: float = 0.0
    positional: float = 0.0

    def to_tuple(self) -> Tuple[float, float, float, float]:
        return (self.safety, self.feasibility, self.milestone, self.positional)

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, GoalVector):
            return NotImplemented
        return self.to_tuple() < other.to_tuple()

    def __le__(self, other: Any) -> bool:
        if not isinstance(other, GoalVector):
            return NotImplemented
        return self.to_tuple() <= other.to_tuple()

    def __gt__(self, other: Any) -> bool:
        if not isinstance(other, GoalVector):
            return NotImplemented
        return self.to_tuple() > other.to_tuple()

    def __ge__(self, other: Any) -> bool:
        if not isinstance(other, GoalVector):
            return NotImplemented
        return self.to_tuple() >= other.to_tuple()

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, GoalVector):
            return False
        return self.to_tuple() == other.to_tuple()

    def as_dict(self) -> Dict[str, float]:
        return {
            "safety": round(self.safety, 3),
            "feasibility": round(self.feasibility, 3),
            "milestone": round(self.milestone, 3),
            "positional": round(self.positional, 3),
            "total_heuristic": round(
                self.safety + self.feasibility + self.milestone + self.positional, 3
            ),
        }

    def __repr__(self) -> str:
        return (
            f"V<safe={self.safety:.1f}, feas={self.feasibility:.1f}, "
            f"mile={self.milestone:.1f}, pos={self.positional:.2f}>"
        )


class GoalEvaluator:
    """
    Evaluates chess positions using Machiavelli's 4-component lexicographical vector.
    """

    MATE_PENALTY = 100000.0
    IMPOSSIBLE_PENALTY = 10000.0
    FEASIBLE_BONUS = 100.0
    COMPLETED_BONUS = 10000.0
    AT_RISK_PENALTY = 100.0

    def __init__(self, our_color: chess.Color = chess.WHITE):
        self.our_color = our_color
        self.feasibility_engine = FeasibilityEngine(our_color=our_color)

    def evaluate(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        uci_score: Optional[Union[UCIScore, int, float]] = None,
    ) -> GoalVector:
        """
        Computes V(s) = <V_safety, V_feasibility, V_milestone, V_positional>.
        """
        v_safety = self.evaluate_safety(board, uci_score)
        v_feasibility = self.evaluate_feasibility(board, goal, tracker)
        v_milestone = self.evaluate_milestone(board, goal, tracker)
        v_positional = self.evaluate_positional(board, uci_score)

        return GoalVector(
            safety=v_safety,
            feasibility=v_feasibility,
            milestone=v_milestone,
            positional=v_positional,
        )

    # -------------------------------------------------------------------------
    # 1. Safety Component (V_safety)
    # -------------------------------------------------------------------------
    def evaluate_safety(
        self,
        board: chess.Board,
        uci_score: Optional[Union[UCIScore, int, float]] = None,
    ) -> float:
        """
        Forced-mate and survival detection.
        - Checkmate against us: -100,000
        - Forced mate against us in k plies: -50,000 - (100 - k) * 100
        - Normal / safe positions: 0.0 (NO -600cp veto!).
        - Note: Delivering checkmate is handled via Feasibility and Milestone completion,
          not by inflating Safety (which would bypass milestone constraints).
        """
        # 1. Terminal board checks
        if board.is_checkmate():
            if board.turn == self.our_color:
                # We are checkmated!
                return -self.MATE_PENALTY
            else:
                # Opponent is checkmated! We survived and delivered checkmate.
                return 0.0

        # 2. Checkmate threat from Stockfish score (if provided)
        if uci_score is not None:
            if isinstance(uci_score, UCIScore):
                mate = uci_score.mate
                if mate is not None:
                    # In python-chess / Stockfish UCI, mate > 0 means side-to-move delivers mate.
                    # Mate < 0 means side-to-move is being mated.
                    is_our_turn = (board.turn == self.our_color)
                    we_get_mated = (is_our_turn and mate < 0) or (not is_our_turn and mate > 0)
                    dist = abs(mate)

                    if we_get_mated:
                        return -50000.0 - max(0, 100 - dist) * 100.0
            elif isinstance(uci_score, (int, float)):
                # If score is represented as an extreme integer (e.g. mate against us)
                if uci_score <= -9000:
                    return -self.MATE_PENALTY / 2.0

        # Position is tactically safe from forced mate
        return 0.0

    # -------------------------------------------------------------------------
    # 2. Feasibility Component (V_feasibility)
    # -------------------------------------------------------------------------
    def evaluate_feasibility(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
    ) -> float:
        """
        Rejection of moves leading to PROVEN_IMPOSSIBLE.
        Reward for COMPLETED goals, mild penalty for AT_RISK entities.
        """
        report = self.feasibility_engine.evaluate(board, goal, tracker)

        if report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE:
            return -self.IMPOSSIBLE_PENALTY
        elif report.status == FeasibilityStatus.COMPLETED:
            return self.COMPLETED_BONUS
        elif report.status == FeasibilityStatus.AT_RISK:
            # Minor penalty proportional to threatened entities
            threat_penalty = len(report.threatened_entities) * 30.0
            return -min(self.AT_RISK_PENALTY, threat_penalty)
        elif report.status == FeasibilityStatus.FEASIBLE:
            return self.FEASIBLE_BONUS
        else:  # UNRESOLVED
            return 0.0

    # -------------------------------------------------------------------------
    # 3. Milestone Component (V_milestone)
    # -------------------------------------------------------------------------
    def evaluate_milestone(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
    ) -> float:
        """
        Evaluates concrete goal progress:
        - Completed milestones: +1000 each
        - Active milestone progress metrics:
          * Sacrifice milestones: confirmed genuine sacrifices + bait placement on attacked squares
          * Promotion milestones: surviving pawn ranks, passed pawn bonuses, 7th rank bonuses
          * Checkmate milestones: opponent king restriction, mating net distance, checks
        """
        score = 0.0

        # 1. Credit for already completed milestones
        for m in goal.milestones:
            if m.is_completed():
                score += 1000.0

        # 2. Progress on active milestones
        active_milestones = goal.get_active_milestones()
        if not active_milestones:
            # If all are completed or none are active, base credit on completed milestones
            return score

        for m in active_milestones:
            m_score = self._evaluate_single_milestone(board, m, tracker)
            score += m_score

        return score

    def _evaluate_single_milestone(
        self,
        board: chess.Board,
        milestone: Milestone,
        tracker: PieceTracker,
    ) -> float:
        """Computes sub-score for a single active milestone."""
        score = 0.0
        opp_color = not self.our_color

        # ---------------------------------------------------------------------
        # Case A: Sacrifice Milestones
        # ---------------------------------------------------------------------
        if milestone.milestone_type in {
            MilestoneType.SACRIFICE_PIECE,
            MilestoneType.SACRIFICE_QUEEN,
            MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
        }:
            confirmed = tracker.get_confirmed_sacrifices(self.our_color)
            score += len(confirmed) * 500.0

            # Bait evaluation: are un-sacrificed target pieces on attacked squares?
            orig_pieces = tracker.get_original_major_minor_pieces(self.our_color)
            sacrificed_ids = {s.piece_id for s in confirmed}

            for p in orig_pieces:
                if p.is_captured or p.piece_id in sacrificed_ids:
                    continue

                if milestone.milestone_type == MilestoneType.SACRIFICE_QUEEN and p.piece_type != chess.QUEEN:
                    continue

                sq = p.current_square
                if sq is not None:
                    # Is this square attacked by opponent?
                    if board.is_attacked_by(opp_color, sq):
                        attackers = len(board.attackers(opp_color, sq))
                        defenders = len(board.attackers(self.our_color, sq))

                        # If undefended or under-defended: high bait score!
                        if defenders == 0:
                            score += 200.0
                        elif attackers > defenders:
                            score += 150.0
                        else:
                            score += 50.0

                    # Forward presence / active baiting bonus
                    rank = chess.square_rank(sq)
                    advancement = (rank - 0) if self.our_color == chess.WHITE else (7 - rank)
                    score += advancement * 8.0

        # ---------------------------------------------------------------------
        # Case B: Pawn Promotion Milestones
        # ---------------------------------------------------------------------
        elif milestone.milestone_type in {
            MilestoneType.PROMOTE_PAWN,
            MilestoneType.PROMOTE_SURVIVING_PAWNS,
            MilestoneType.PROMOTE_ALL_8_PAWNS,
        }:
            target_piece_type = chess.KNIGHT
            if milestone.target_piece_types:
                t_str = milestone.target_piece_types[0].lower()
                if "knight" in t_str:
                    target_piece_type = chess.KNIGHT
                elif "queen" in t_str:
                    target_piece_type = chess.QUEEN
                elif "rook" in t_str:
                    target_piece_type = chess.ROOK
                elif "bishop" in t_str:
                    target_piece_type = chess.BISHOP

            # Credit for already promoted pieces of target type
            promoted = tracker.get_promoted_pieces(self.our_color, target_piece_type)
            score += len(promoted) * 800.0

            # Credit for other promoted pieces (if any)
            other_promoted = [p for p in tracker.get_promoted_pieces(self.our_color) if p.piece_type != target_piece_type]
            score += len(other_promoted) * 400.0

            # Advancement of surviving pawns
            surviving = tracker.get_surviving_pawns(self.our_color)
            for p in surviving:
                sq = p.current_square
                if sq is None:
                    continue

                file_idx = chess.square_file(sq)
                rank_idx = chess.square_rank(sq)

                # Distance to promotion
                if self.our_color == chess.WHITE:
                    rank_progress = rank_idx - 1  # 2nd rank = 0, 7th rank = 5
                    is_seventh = (rank_idx == 6)
                    promo_sq = chess.square(file_idx, 7)
                else:
                    rank_progress = 6 - rank_idx  # 7th rank = 0, 2nd rank = 5
                    is_seventh = (rank_idx == 1)
                    promo_sq = chess.square(file_idx, 0)

                # Rank advancement score
                score += rank_progress * 40.0

                # 7th rank / 1 step away bonus
                if is_seventh:
                    score += 250.0

                # Check if pawn is passed
                if self._is_passed_pawn(board, sq, self.our_color):
                    score += 80.0

                # Promotion square control: do we control the promotion square?
                if board.is_attacked_by(self.our_color, promo_sq):
                    score += 30.0

                # Supported pawn (defended by our pieces/pawns)
                if board.is_attacked_by(self.our_color, sq):
                    score += 25.0

            # King escort: proximity of our King to advancing pawns
            our_king_sq = board.king(self.our_color)
            if our_king_sq is not None and surviving:
                avg_pawn_dist = sum(
                    chess.square_distance(our_king_sq, p.current_square)
                    for p in surviving if p.current_square is not None
                ) / max(1, len(surviving))
                score += max(0.0, (7.0 - avg_pawn_dist) * 10.0)

        # ---------------------------------------------------------------------
        # Case C: Checkmate With Piece / Mating Net Milestones
        # ---------------------------------------------------------------------
        elif milestone.milestone_type in {
            MilestoneType.CHECKMATE_WITH_PIECE,
            MilestoneType.WIN_GAME,
        }:
            target_types = milestone.target_piece_types or ["knight"]
            req_promoted = milestone.conditions.get("require_promoted_lineage", False)

            # Target pieces
            matching_pieces: List[TrackedPiece] = []
            for t_name in target_types:
                pt = chess.KNIGHT if "knight" in t_name.lower() else chess.QUEEN
                if req_promoted:
                    matching_pieces.extend(tracker.get_promoted_pieces(self.our_color, pt))
                else:
                    matching_pieces.extend([
                        p for p in tracker.pieces.values()
                        if p.color == self.our_color and p.piece_type == pt and not p.is_captured
                    ])

            opp_king_sq = board.king(opp_color)
            our_king_sq = board.king(self.our_color)

            if opp_king_sq is not None:
                # 1. Opponent king restriction (mating net tightness)
                legal_king_escapes = self._count_king_legal_moves(board, opp_color, opp_king_sq)
                score += max(0.0, (8.0 - legal_king_escapes) * 30.0)

                # 2. Checks delivered
                if board.is_check() and board.turn == opp_color:
                    score += 60.0

                # 3. Target pieces proximity to enemy king
                for p in matching_pieces:
                    if p.current_square is not None:
                        dist = chess.square_distance(p.current_square, opp_king_sq)
                        score += max(0.0, (7.0 - dist) * 25.0)

                # 4. Our king proximity to enemy king (for endgame mate)
                if our_king_sq is not None:
                    k_dist = chess.square_distance(our_king_sq, opp_king_sq)
                    score += max(0.0, (7.0 - k_dist) * 15.0)

        return score

    # -------------------------------------------------------------------------
    # 4. Positional Component (V_positional / V_tactical_compensation)
    # -------------------------------------------------------------------------
    def evaluate_positional(
        self,
        board: chess.Board,
        uci_score: Optional[Union[UCIScore, int, float]] = None,
    ) -> float:
        """
        Conventional Stockfish evaluation or static heuristic used as tie-breaker.
        Normalizes Stockfish centipawns to approximately [-10.0, 10.0].
        """
        if uci_score is not None:
            if isinstance(uci_score, UCIScore):
                cp = uci_score.score_for_white(self.our_color == chess.WHITE)
                return max(-20.0, min(20.0, cp / 100.0))
            elif isinstance(uci_score, (int, float)):
                return max(-20.0, min(20.0, float(uci_score) / 100.0))

        # Static heuristic fallback if engine score is absent
        return self._static_positional_score(board)

    def _static_positional_score(self, board: chess.Board) -> float:
        """Quick heuristic for material balance, mobility, and center control."""
        material = 0
        for sq, piece in board.piece_map().items():
            val = PIECE_VALUES.get(piece.piece_type, 0)
            if piece.color == self.our_color:
                material += val
            else:
                material -= val

        # Center control bonus (d4, e4, d5, e5)
        center_control = 0
        center_squares = (chess.D4, chess.E4, chess.D5, chess.E5)
        for c_sq in center_squares:
            if board.is_attacked_by(self.our_color, c_sq):
                center_control += 1
            if board.is_attacked_by(not self.our_color, c_sq):
                center_control -= 1

        return (material * 0.5) + (center_control * 0.1)

    # -------------------------------------------------------------------------
    # Helper Utilities
    # -------------------------------------------------------------------------
    @staticmethod
    def _is_passed_pawn(board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
        """Check if pawn at square has no opposing pawns in front on same or adjacent files."""
        file_idx = chess.square_file(square)
        rank_idx = chess.square_rank(square)
        opp_color = not color

        files_to_check = [f for f in (file_idx - 1, file_idx, file_idx + 1) if 0 <= f <= 7]

        for f in files_to_check:
            if color == chess.WHITE:
                for r in range(rank_idx + 1, 8):
                    sq = chess.square(f, r)
                    piece = board.piece_at(sq)
                    if piece and piece.color == opp_color and piece.piece_type == chess.PAWN:
                        return False
            else:
                for r in range(0, rank_idx):
                    sq = chess.square(f, r)
                    piece = board.piece_at(sq)
                    if piece and piece.color == opp_color and piece.piece_type == chess.PAWN:
                        return False
        return True

    @staticmethod
    def _count_king_legal_moves(board: chess.Board, king_color: chess.Color, king_sq: chess.Square) -> int:
        """Count available escape squares for the king."""
        escapes = 0
        opp_color = not king_color
        for target in board.attacks(king_sq):
            occupant = board.piece_at(target)
            if occupant is not None and occupant.color == king_color:
                continue  # Blocked by own piece
            if not board.is_attacked_by(opp_color, target):
                escapes += 1
        return escapes
