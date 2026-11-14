"""Machiavelli Hybrid Candidate Generator.

Combines Stockfish MultiPV tactical lines with goal-directed candidate moves:
- Pawn pushes & designated underpromotions (e.g., surviving pawns -> knights)
- Deliberate sacrifice candidate moves onto attacked squares (NEVER the King!)
- Clearance moves and King walks escorting pawns
- Mating net maneuvers and restricting checks

Includes Adaptive Candidate Expansion to widen the search beam when no viable
goal-advancing continuation is found in the initial candidate set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
import chess

from backend.app.chess_engine.goal_schema import (
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import (
    PIECE_VALUES,
    PieceTracker,
    SacrificeIntent,
    TrackedPiece,
)
from backend.app.chess_engine.uci_client import CandidateMove, UCIScore


class CandidateCategory(str, Enum):
    TACTICAL = "tactical"
    PROMOTION_ADVANCE = "promotion_advance"
    UNDERPROMOTION = "underpromotion"
    SACRIFICE_OFFER = "sacrifice_offer"
    CLEARANCE = "clearance"
    KING_WALK = "king_walk"
    MATING_NET = "mating_net"


@dataclass
class TaggedCandidate:
    """A chess move tagged with semantic intent, categories, and evaluation metadata."""
    move: chess.Move
    categories: Set[CandidateCategory] = field(default_factory=set)
    san: Optional[str] = None
    uci_score: Optional[UCIScore] = None
    pv: List[str] = field(default_factory=list)
    multipv: Optional[int] = None
    priority: float = 0.0
    sacrifice_intent: Optional[SacrificeIntent] = None
    target_piece_id: Optional[str] = None
    target_milestone_id: Optional[str] = None
    explanation_note: Optional[str] = None

    @property
    def uci(self) -> str:
        return self.move.uci()

    def has_category(self, cat: CandidateCategory) -> bool:
        return cat in self.categories

    def to_dict(self) -> Dict[str, Any]:
        return {
            "move": self.move.uci(),
            "san": self.san,
            "categories": [c.value for c in self.categories],
            "priority": round(self.priority, 2),
            "score": self.uci_score.to_cp() if self.uci_score else None,
            "is_sacrifice": CandidateCategory.SACRIFICE_OFFER in self.categories,
            "explanation": self.explanation_note,
            "pv": self.pv,
        }


class CandidateGenerator:
    """
    Generates and orders candidate moves for Machiavelli's adversarial search.
    """

    def __init__(self, our_color: chess.Color = chess.WHITE):
        self.our_color = our_color

    def generate_candidates(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        stockfish_candidates: Optional[List[CandidateMove]] = None,
        max_candidates: int = 16,
    ) -> List[TaggedCandidate]:
        """
        Generates a hybrid set of tactical and goal-directed moves.
        """
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return []

        candidates_map: Dict[str, TaggedCandidate] = {}
        active_milestones = goal.get_active_milestones()
        primary_milestone = active_milestones[0] if active_milestones else None

        # -------------------------------------------------------------
        # 1. Ingest Stockfish MultiPV Tactical Candidates
        # -------------------------------------------------------------
        if stockfish_candidates:
            for sc in stockfish_candidates:
                try:
                    m = chess.Move.from_uci(sc.move)
                    if m in board.legal_moves:
                        cand = TaggedCandidate(
                            move=m,
                            categories={CandidateCategory.TACTICAL},
                            san=sc.san or board.san(m),
                            uci_score=sc.score,
                            pv=sc.pv,
                            multipv=sc.multipv,
                            priority=100.0 - (sc.multipv * 5.0),
                            explanation_note=f"Stockfish MultiPV #{sc.multipv}",
                        )
                        candidates_map[m.uci()] = cand
                except Exception:
                    continue

        # -------------------------------------------------------------
        # 2. Goal-Directed Candidate Generation
        # -------------------------------------------------------------
        for move in legal_moves:
            uci_str = move.uci()
            piece = board.piece_at(move.from_square)
            if piece is None or piece.color != self.our_color:
                continue

            existing = candidates_map.get(uci_str)
            tagged = existing or TaggedCandidate(
                move=move,
                san=board.san(move),
                priority=0.0,
            )

            # Check: Pawn Advancement & Promotions
            if piece.piece_type == chess.PAWN:
                self._tag_pawn_move(board, move, tagged, primary_milestone, tracker)

            # Check: Intentional Sacrifices (NEVER THE KING)
            elif piece.piece_type != chess.KING:
                self._tag_sacrifice_candidate(
                    board, move, piece, tagged, primary_milestone, tracker
                )

            # Check: King Walks & Clearances
            if piece.piece_type == chess.KING:
                self._tag_king_walk(board, move, tagged, primary_milestone, tracker)
            else:
                self._tag_clearance_move(board, move, tagged, primary_milestone)

            # Check: Mating Net & Checks
            if board.gives_check(move):
                tagged.categories.add(CandidateCategory.MATING_NET)
                tagged.priority += 40.0

            if primary_milestone and primary_milestone.milestone_type in {
                MilestoneType.CHECKMATE_WITH_PIECE,
                MilestoneType.WIN_GAME,
            }:
                self._tag_mating_net_move(board, move, piece, tagged, primary_milestone, tracker)

            # Add to map if tagged with any goal category or was from Stockfish
            if tagged.categories:
                candidates_map[uci_str] = tagged

        # Fallback: if map is still empty, include all legal moves
        if not candidates_map:
            for move in legal_moves:
                candidates_map[move.uci()] = TaggedCandidate(
                    move=move,
                    san=board.san(move),
                    priority=1.0,
                )

        # -------------------------------------------------------------
        # 3. Sort Candidates by Priority
        # -------------------------------------------------------------
        sorted_candidates = sorted(
            candidates_map.values(), key=lambda c: c.priority, reverse=True
        )

        return sorted_candidates[:max_candidates]

    def expand_candidates(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        current_candidates: List[TaggedCandidate],
        max_expanded: int = 30,
    ) -> List[TaggedCandidate]:
        """
        Adaptive Candidate Expansion:
        Expands the search beam when top candidates fail to advance the active milestone.
        Generates all legal pawn moves, un-sacrificed piece moves, checks, and king escapes.
        """
        current_ucis = {c.move.uci() for c in current_candidates}
        expanded = list(current_candidates)
        active_milestones = goal.get_active_milestones()
        primary_milestone = active_milestones[0] if active_milestones else None

        for move in board.legal_moves:
            if move.uci() in current_ucis:
                continue

            piece = board.piece_at(move.from_square)
            if piece is None or piece.color != self.our_color:
                continue

            cand = TaggedCandidate(move=move, san=board.san(move), priority=10.0)

            # If promotion milestone, add all pawn moves
            if primary_milestone and primary_milestone.milestone_type in {
                MilestoneType.PROMOTE_PAWN,
                MilestoneType.PROMOTE_SURVIVING_PAWNS,
                MilestoneType.PROMOTE_ALL_8_PAWNS,
            }:
                if piece.piece_type == chess.PAWN:
                    self._tag_pawn_move(board, move, cand, primary_milestone, tracker)
                    cand.priority += 50.0
                    expanded.append(cand)
                    continue

            # If sacrifice milestone, add any move offering major/minor piece
            if primary_milestone and primary_milestone.milestone_type in {
                MilestoneType.SACRIFICE_PIECE,
                MilestoneType.SACRIFICE_QUEEN,
                MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
            }:
                if piece.piece_type != chess.KING:
                    self._tag_sacrifice_candidate(
                        board, move, piece, cand, primary_milestone, tracker
                    )
                    if CandidateCategory.SACRIFICE_OFFER in cand.categories:
                        cand.priority += 60.0
                        expanded.append(cand)
                        continue

            # Add any checks
            if board.gives_check(move):
                cand.categories.add(CandidateCategory.MATING_NET)
                cand.priority += 35.0
                expanded.append(cand)
                continue

            # Add captures
            if board.is_capture(move):
                cand.categories.add(CandidateCategory.TACTICAL)
                cand.priority += 20.0
                expanded.append(cand)

        expanded.sort(key=lambda c: c.priority, reverse=True)
        return expanded[:max_expanded]

    # -------------------------------------------------------------------------
    # Internal Tagging Helpers
    # -------------------------------------------------------------------------
    def _tag_pawn_move(
        self,
        board: chess.Board,
        move: chess.Move,
        cand: TaggedCandidate,
        milestone: Optional[Milestone],
        tracker: PieceTracker,
    ) -> None:
        """Tags pawn pushes, promotions, and designated underpromotions."""
        cand.categories.add(CandidateCategory.PROMOTION_ADVANCE)

        # Check underpromotion / promotion
        if move.promotion is not None:
            # Check if milestone specifically wants knights
            target_types = (milestone.target_piece_types if milestone else []) or ["knight"]
            wants_knight = any("knight" in t.lower() for t in target_types)

            if move.promotion == chess.KNIGHT and wants_knight:
                cand.categories.add(CandidateCategory.UNDERPROMOTION)
                cand.priority += 300.0
                cand.explanation_note = "Underpromotion to designated Knight"
            elif move.promotion == chess.QUEEN and not wants_knight:
                cand.categories.add(CandidateCategory.UNDERPROMOTION)
                cand.priority += 250.0
                cand.explanation_note = "Promotion to Queen"
            else:
                cand.priority += 120.0
            return

        # Rank advancement boost
        from_rank = chess.square_rank(move.from_square)
        to_rank = chess.square_rank(move.to_square)
        progress = (to_rank - from_rank) if self.our_color == chess.WHITE else (from_rank - to_rank)

        cand.priority += progress * 25.0

        # One step from promotion (reaching 7th rank for White / 2nd rank for Black)
        is_seventh = (to_rank == 6) if self.our_color == chess.WHITE else (to_rank == 1)
        if is_seventh:
            cand.priority += 150.0
            cand.explanation_note = "Pawn advanced to 7th rank (1 square from promotion)"
        else:
            cand.explanation_note = f"Pawn advanced to rank {to_rank + 1}"

    def _tag_sacrifice_candidate(
        self,
        board: chess.Board,
        move: chess.Move,
        piece: chess.Piece,
        cand: TaggedCandidate,
        milestone: Optional[Milestone],
        tracker: PieceTracker,
    ) -> None:
        """
        Tags deliberate sacrifice candidates.
        RULE: King is STRICTLY excluded.
        Evaluates moves onto attacked squares where material is given up for lesser/zero.
        """
        if piece.piece_type == chess.KING:
            return  # The King is strictly excluded from sacrifice objectives

        opp_color = not self.our_color
        is_sacrifice_milestone = milestone and milestone.milestone_type in {
            MilestoneType.SACRIFICE_PIECE,
            MilestoneType.SACRIFICE_QUEEN,
            MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES,
        }

        # Check if piece is an original piece that still needs sacrificing
        tracked_p = tracker.get_piece_at(move.from_square)
        if not tracked_p or not tracked_p.is_original:
            return

        if milestone and milestone.milestone_type == MilestoneType.SACRIFICE_QUEEN:
            if piece.piece_type != chess.QUEEN:
                return

        # Check if destination square is attacked by opponent
        to_sq = move.to_square
        is_attacked = board.is_attacked_by(opp_color, to_sq)

        if is_attacked:
            captured_by_us = board.piece_at(to_sq)
            mat_captured = PIECE_VALUES.get(captured_by_us.piece_type, 0) if captured_by_us else 0
            offered_val = PIECE_VALUES.get(piece.piece_type, 0)
            net_loss = offered_val - mat_captured

            # True sacrifice: giving up material for lesser or zero material
            if net_loss > 0:
                cand.categories.add(CandidateCategory.SACRIFICE_OFFER)
                m_id = milestone.id if milestone else "milestone_sacrifice"

                # Intent declaration
                intent = SacrificeIntent(
                    piece_id=tracked_p.piece_id,
                    milestone_id=m_id,
                    move=move,
                    offered_square=to_sq,
                    offered_piece_type=piece.piece_type,
                    offering_ply=tracker.ply_counter,
                    material_captured_on_offer=mat_captured,
                )
                cand.sacrifice_intent = intent
                cand.target_piece_id = tracked_p.piece_id
                cand.target_milestone_id = m_id

                bonus = 180.0 if is_sacrifice_milestone else 40.0
                cand.priority += bonus + (net_loss * 15.0)
                cand.explanation_note = (
                    f"Intentional {chess.piece_name(piece.piece_type)} sacrifice offer "
                    f"on {chess.square_name(to_sq)}"
                )

    def _tag_king_walk(
        self,
        board: chess.Board,
        move: chess.Move,
        cand: TaggedCandidate,
        milestone: Optional[Milestone],
        tracker: PieceTracker,
    ) -> None:
        """Tags King escort moves supporting advancing pawns or mating nets."""
        cand.categories.add(CandidateCategory.KING_WALK)
        surviving_pawns = tracker.get_surviving_pawns(self.our_color)

        if surviving_pawns:
            # Measure distance to closest surviving pawn
            old_dist = min(
                chess.square_distance(move.from_square, p.current_square)
                for p in surviving_pawns if p.current_square is not None
            )
            new_dist = min(
                chess.square_distance(move.to_square, p.current_square)
                for p in surviving_pawns if p.current_square is not None
            )
            if new_dist < old_dist:
                cand.priority += 35.0
                cand.explanation_note = "King walking to escort advancing pawn"
        else:
            cand.priority += 5.0

    def _tag_clearance_move(
        self,
        board: chess.Board,
        move: chess.Move,
        cand: TaggedCandidate,
        milestone: Optional[Milestone],
    ) -> None:
        """Tags moves that unblock paths for advancing pawns."""
        from_sq = move.from_square
        from_file = chess.square_file(from_sq)
        from_rank = chess.square_rank(from_sq)

        # Check if our pawn is behind this square on the same file
        behind_rank = from_rank - 1 if self.our_color == chess.WHITE else from_rank + 1
        if 0 <= behind_rank <= 7:
            behind_sq = chess.square(from_file, behind_rank)
            piece_behind = board.piece_at(behind_sq)
            if (
                piece_behind
                and piece_behind.color == self.our_color
                and piece_behind.piece_type == chess.PAWN
            ):
                cand.categories.add(CandidateCategory.CLEARANCE)
                cand.priority += 45.0
                cand.explanation_note = f"Clearance move opening file {chess.FILE_NAMES[from_file]} for pawn"

    def _tag_mating_net_move(
        self,
        board: chess.Board,
        move: chess.Move,
        piece: chess.Piece,
        cand: TaggedCandidate,
        milestone: Milestone,
        tracker: PieceTracker,
    ) -> None:
        """Tags moves maneuvering designated mating pieces (e.g. Knights) toward enemy king."""
        opp_color = not self.our_color
        opp_king_sq = board.king(opp_color)
        if opp_king_sq is None:
            return

        target_types = milestone.target_piece_types or ["knight"]
        req_promoted = milestone.conditions.get("require_promoted_lineage", False)

        is_designated_piece = False
        if "knight" in [t.lower() for t in target_types] and piece.piece_type == chess.KNIGHT:
            if req_promoted:
                tracked = tracker.get_piece_at(move.from_square)
                is_designated_piece = (tracked is not None and tracked.is_promoted)
            else:
                is_designated_piece = True

        if is_designated_piece:
            old_dist = chess.square_distance(move.from_square, opp_king_sq)
            new_dist = chess.square_distance(move.to_square, opp_king_sq)
            if new_dist < old_dist:
                cand.categories.add(CandidateCategory.MATING_NET)
                cand.priority += 60.0
                cand.explanation_note = f"Maneuvering mating piece closer to enemy King (distance {new_dist})"
