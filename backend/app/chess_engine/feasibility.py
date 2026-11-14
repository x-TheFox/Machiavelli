from __future__ import annotations

from typing import Any, Dict, List, Optional
import chess

from backend.app.chess_engine.goal_schema import (
    FeasibilityReport,
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import PieceTracker, TrackedPiece


class FeasibilityEngine:
    """
    Exact proof-based impossibility engine.
    
    CRITICAL CONTRACT:
    A failed search, engine timeout, or horizon limit MUST NEVER be interpreted
    as impossibility (status remains UNRESOLVED).
    
    Status transitions to PROVEN_IMPOSSIBLE ONLY when formal mathematical/logical
    invariants are irreversibly broken.
    """

    def __init__(self, our_color: chess.Color = chess.WHITE):
        self.our_color = our_color

    def evaluate(
        self,
        board: chess.Board,
        goal: GoalDefinition,
        tracker: PieceTracker,
        is_search_timeout: bool = False,
    ) -> FeasibilityReport:
        """
        Evaluates current board state, piece tracker, and goal definition for impossibility proofs,
        tactical threats (AT_RISK), completion, or unresolved status.
        """
        opp_color = not self.our_color

        # -------------------------------------------------------------
        # 1. Terminal Game State Proofs
        # -------------------------------------------------------------
        # 1a. Checkmate against us (We lost)
        if board.is_checkmate() and board.turn == self.our_color:
            return FeasibilityReport(
                status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                reason="Our King is checkmated; game is lost.",
                evidence={"terminal": "checkmate_against_us", "ply": board.ply()},
            )

        # 1b. Checkmate delivered by us
        if board.is_checkmate() and board.turn == opp_color:
            all_sacs_done = tracker.all_original_pieces_sacrificed(self.our_color) if any(
                m.milestone_type == MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES for m in goal.milestones
            ) else True
            q_sac_done = tracker.is_queen_sacrificed(self.our_color) if any(
                m.milestone_type == MilestoneType.SACRIFICE_QUEEN for m in goal.milestones
            ) else True
            pawns_done = (len(tracker.get_surviving_pawns(self.our_color)) == 0 and len(tracker.get_promoted_pieces(self.our_color)) > 0) if any(
                m.milestone_type in {MilestoneType.PROMOTE_PAWN, MilestoneType.PROMOTE_SURVIVING_PAWNS, MilestoneType.PROMOTE_ALL_8_PAWNS} for m in goal.milestones
            ) else True

            if all_sacs_done and q_sac_done and pawns_done:
                return FeasibilityReport(
                    status=FeasibilityStatus.COMPLETED,
                    reason="All milestones and final checkmate verified!",
                    evidence={"ply": board.ply(), "checkmate": True},
                )
            else:
                return FeasibilityReport(
                    status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                    reason="Game terminated by premature checkmate before prerequisite milestones were completed.",
                    evidence={"terminal": "premature_checkmate", "ply": board.ply()},
                )

        # 1c. Stalemate or Draw when win/checkmate is required
        if board.is_stalemate():
            return FeasibilityReport(
                status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                reason="Game ended in stalemate; checkmate/win cannot be achieved.",
                evidence={"terminal": "stalemate", "ply": board.ply()},
            )

        if board.is_insufficient_material():
            # If win or mate is part of goal, insufficient material makes it impossible
            return FeasibilityReport(
                status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                reason="Draw by insufficient material; cannot force checkmate.",
                evidence={"terminal": "insufficient_material", "fen": board.fen()},
            )

        if board.is_seventyfive_moves() or board.is_fivefold_repetition():
            return FeasibilityReport(
                status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                reason="Game drawn by mandatory rules (75-move or 5-fold repetition).",
                evidence={"terminal": "mandatory_draw", "ply": board.ply()},
            )

        # -------------------------------------------------------------
        # 2. Global Invariant Proofs
        # -------------------------------------------------------------
        for inv in goal.invariants:
            # Check max moves
            if inv.max_moves is not None:
                # fullmove_number starts at 1
                if board.fullmove_number > inv.max_moves and not goal.is_all_completed():
                    return FeasibilityReport(
                        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                        reason=f"Move limit of {inv.max_moves} full moves exceeded (current: {board.fullmove_number}).",
                        broken_invariant_id=inv.id,
                        evidence={"current_move": board.fullmove_number, "max_moves": inv.max_moves},
                    )

            # Check zero / max captures
            if inv.max_our_captures is not None:
                our_captures = sum(
                    1 for p in tracker.pieces.values()
                    if p.color == opp_color and p.is_captured and p.captured_by_color == self.our_color
                )
                if our_captures > inv.max_our_captures:
                    return FeasibilityReport(
                        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                        reason=f"Capture limit exceeded: made {our_captures} captures, max allowed is {inv.max_our_captures}.",
                        broken_invariant_id=inv.id,
                        evidence={"our_captures": our_captures, "max_allowed": inv.max_our_captures},
                    )

            # Check no pawn losses
            if inv.no_pawn_losses:
                lost_pawns = [
                    p.piece_id for p in tracker.get_original_pawns(self.our_color) if p.is_captured
                ]
                if lost_pawns:
                    return FeasibilityReport(
                        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                        reason=f"Invariant no_pawn_losses violated: pawn(s) {lost_pawns} captured.",
                        broken_invariant_id=inv.id,
                        evidence={"lost_pawns": lost_pawns},
                    )

        # -------------------------------------------------------------
        # 3. Milestone-Specific Impossibility Proofs
        # -------------------------------------------------------------
        surviving_pawns = tracker.get_surviving_pawns(self.our_color)
        promoted_pieces = tracker.get_promoted_pieces(self.our_color)

        for m in goal.milestones:
            if m.is_completed():
                continue

            # 3a. SACRIFICE_ALL_ORIGINAL_PIECES
            if m.milestone_type == MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES:
                orig_pieces = tracker.get_original_major_minor_pieces(self.our_color)
                sacrificed_ids = {
                    s.piece_id for s in tracker.get_confirmed_sacrifices(self.our_color)
                }
                # Check if any original piece died without a genuine sacrifice
                for p in orig_pieces:
                    if p.is_captured and p.piece_id not in sacrificed_ids:
                        return FeasibilityReport(
                            status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                            reason=(
                                f"Original piece {p.piece_id} ({chess.piece_name(p.piece_type)}) "
                                f"was lost without genuine sacrifice. Objective requires sacrificing ALL 7 original pieces."
                            ),
                            failed_milestone_id=m.id,
                            evidence={"piece_id": p.piece_id, "piece_type": chess.piece_name(p.piece_type)},
                        )

            # 3b. SACRIFICE_QUEEN
            elif m.milestone_type == MilestoneType.SACRIFICE_QUEEN:
                sacrificed_queen = tracker.is_queen_sacrificed(self.our_color)
                if not sacrificed_queen:
                    orig_queens = [
                        p for p in tracker.pieces.values()
                        if p.color == self.our_color and p.is_original and p.piece_type == chess.QUEEN
                    ]
                    for q in orig_queens:
                        if q.is_captured:
                            # Original queen lost without genuine sacrifice
                            return FeasibilityReport(
                                status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                                reason="Original queen was captured without genuine sacrifice.",
                                failed_milestone_id=m.id,
                                evidence={"queen_id": q.piece_id},
                            )

            # 3c. PROMOTE_ALL_8_PAWNS
            elif m.milestone_type == MilestoneType.PROMOTE_ALL_8_PAWNS:
                orig_pawns = tracker.get_original_pawns(self.our_color)
                captured_orig_pawns = [p for p in orig_pawns if p.is_captured]
                if captured_orig_pawns:
                    return FeasibilityReport(
                        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                        reason=(
                            f"Original pawn {captured_orig_pawns[0].piece_id} was captured. "
                            f"Impossible to promote all 8 original pawns."
                        ),
                        failed_milestone_id=m.id,
                        evidence={"captured_pawns": [p.piece_id for p in captured_orig_pawns]},
                    )

            # 3d. PROMOTE_SURVIVING_PAWNS
            elif m.milestone_type == MilestoneType.PROMOTE_SURVIVING_PAWNS:
                # Target count is the number of surviving pawns required
                target_count = m.target_count
                promoted_count = len(promoted_pieces)
                current_alive_pawns = len(surviving_pawns)

                if target_count > 0:
                    if (current_alive_pawns + promoted_count) < target_count:
                        return FeasibilityReport(
                            status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                            reason=(
                                f"Required {target_count} surviving pawn promotions, but only "
                                f"{current_alive_pawns} pawns alive and {promoted_count} promoted."
                            ),
                            failed_milestone_id=m.id,
                            evidence={
                                "target": target_count,
                                "alive": current_alive_pawns,
                                "promoted": promoted_count,
                            },
                        )
                else:
                    # Dynamic: if alive pawns is 0 and promoted_count is 0 -> impossible
                    if current_alive_pawns == 0 and promoted_count == 0:
                        return FeasibilityReport(
                            status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                            reason="All pawns were captured before any promotion occurred.",
                            failed_milestone_id=m.id,
                            evidence={"alive": 0, "promoted": 0},
                        )

            # 3e. CHECKMATE_WITH_PIECE (e.g. checkmate using promoted knights)
            elif m.milestone_type == MilestoneType.CHECKMATE_WITH_PIECE:
                req_promoted = m.conditions.get("require_promoted_lineage", False)
                target_types = m.target_piece_types or ["knight"]

                if req_promoted and "knight" in target_types:
                    promoted_knights = tracker.get_promoted_pieces(self.our_color, chess.KNIGHT)
                    if len(promoted_knights) == 0 and len(surviving_pawns) == 0:
                        return FeasibilityReport(
                            status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
                            reason=(
                                "All pawns eliminated and zero promoted knights exist. "
                                "Impossible to deliver checkmate using promoted knights."
                            ),
                            failed_milestone_id=m.id,
                            evidence={"promoted_knights": 0, "surviving_pawns": 0},
                        )

        # -------------------------------------------------------------
        # 4. Check for Completion
        # -------------------------------------------------------------
        if goal.is_all_completed():
            # If goal requires checkmate or win, check board checkmate
            win_required = any(
                m.milestone_type in {MilestoneType.WIN_GAME, MilestoneType.CHECKMATE_WITH_PIECE}
                for m in goal.milestones
            )
            if win_required:
                if board.is_checkmate() and board.turn == opp_color:
                    return FeasibilityReport(
                        status=FeasibilityStatus.COMPLETED,
                        reason="All milestones and final checkmate verified!",
                        evidence={"ply": board.ply()},
                    )
            else:
                return FeasibilityReport(
                    status=FeasibilityStatus.COMPLETED,
                    reason="All milestones verified and completed!",
                    evidence={"ply": board.ply()},
                )

        # -------------------------------------------------------------
        # 5. Search Timeout / Horizon Handling (CRITICAL CONTRACT)
        # -------------------------------------------------------------
        if is_search_timeout:
            # A search timeout MUST NEVER be interpreted as impossibility!
            return FeasibilityReport(
                status=FeasibilityStatus.UNRESOLVED,
                reason="Search budget expired without conclusive tactical proof. Status remains UNRESOLVED.",
                evidence={"search_timeout": True},
            )

        # -------------------------------------------------------------
        # 6. Tactical Threat / AT_RISK Detection
        # -------------------------------------------------------------
        threatened_entities: List[str] = []
        # Check active milestone threats
        active_milestones = goal.get_active_milestones()
        for m in active_milestones:
            if m.milestone_type in {
                MilestoneType.PROMOTE_PAWN,
                MilestoneType.PROMOTE_SURVIVING_PAWNS,
                MilestoneType.PROMOTE_ALL_8_PAWNS,
            }:
                # Check if any pawn needed is under direct attack and en prise
                for p in surviving_pawns:
                    sq = p.current_square
                    if sq is not None and board.is_attacked_by(opp_color, sq):
                        # Count attackers vs defenders
                        attackers = len(board.attackers(opp_color, sq))
                        defenders = len(board.attackers(self.our_color, sq))
                        if attackers > defenders:
                            threatened_entities.append(f"{p.piece_id}@{chess.square_name(sq)}")

            elif m.milestone_type == MilestoneType.CHECKMATE_WITH_PIECE:
                req_promoted = m.conditions.get("require_promoted_lineage", False)
                if req_promoted:
                    for pk in tracker.get_promoted_pieces(self.our_color, chess.KNIGHT):
                        sq = pk.current_square
                        if sq is not None and board.is_attacked_by(opp_color, sq):
                            attackers = len(board.attackers(opp_color, sq))
                            defenders = len(board.attackers(self.our_color, sq))
                            if attackers > defenders:
                                threatened_entities.append(f"{pk.piece_id}@{chess.square_name(sq)}")

        if threatened_entities:
            return FeasibilityReport(
                status=FeasibilityStatus.AT_RISK,
                reason=f"Immediate tactical threats detected on critical entities: {', '.join(threatened_entities)}",
                threatened_entities=threatened_entities,
                evidence={"threatened_count": len(threatened_entities)},
            )

        # -------------------------------------------------------------
        # 7. Default: FEASIBLE
        # -------------------------------------------------------------
        return FeasibilityReport(
            status=FeasibilityStatus.FEASIBLE,
            reason="Goal remains mathematically feasible; active path open.",
            evidence={"active_milestones": [m.id for m in active_milestones]},
        )
