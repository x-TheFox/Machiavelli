from __future__ import annotations

import copy
import uuid
from typing import Dict, List, Optional, Set, Tuple
import chess

# Conventional piece material values
PIECE_VALUES: Dict[chess.PieceType, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 1000,
}


class TrackedPiece:
    """Represents a chess piece with persistent identity across the game."""

    def __init__(
        self,
        piece_id: str,
        color: chess.Color,
        piece_type: chess.PieceType,
        original_square: chess.Square,
        current_square: Optional[chess.Square] = None,
        is_original: bool = True,
        is_promoted: bool = False,
        promoted_from_id: Optional[str] = None,
        promoted_at_ply: Optional[int] = None,
    ):
        self.piece_id = piece_id
        self.color = color
        self.piece_type = piece_type
        self.original_square = original_square
        self.current_square = current_square if current_square is not None else original_square
        self.is_original = is_original
        self.is_promoted = is_promoted
        self.promoted_from_id = promoted_from_id
        self.promoted_at_ply = promoted_at_ply

        self.is_captured: bool = False
        self.captured_at_ply: Optional[int] = None
        self.captured_by_piece_type: Optional[chess.PieceType] = None
        self.captured_by_color: Optional[chess.Color] = None
        self.moves_count: int = 0

    @property
    def is_pawn(self) -> bool:
        return self.piece_type == chess.PAWN

    @property
    def is_king(self) -> bool:
        return self.piece_type == chess.KING

    @property
    def is_major_or_minor(self) -> bool:
        return self.piece_type in {
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
        }

    def clone(self) -> "TrackedPiece":
        cp = TrackedPiece(
            piece_id=self.piece_id,
            color=self.color,
            piece_type=self.piece_type,
            original_square=self.original_square,
            current_square=self.current_square,
            is_original=self.is_original,
            is_promoted=self.is_promoted,
            promoted_from_id=self.promoted_from_id,
            promoted_at_ply=self.promoted_at_ply,
        )
        cp.is_captured = self.is_captured
        cp.captured_at_ply = self.captured_at_ply
        cp.captured_by_piece_type = self.captured_by_piece_type
        cp.captured_by_color = self.captured_by_color
        cp.moves_count = self.moves_count
        return cp

    def __repr__(self) -> str:
        status = "alive" if not self.is_captured else "captured"
        sq = chess.square_name(self.current_square) if self.current_square is not None else "none"
        return f"<TrackedPiece {self.piece_id} {chess.piece_symbol(self.piece_type)}@{sq} {status}>"


class SacrificeIntent:
    """Pre-move declaration of intentional sacrifice targeting a milestone."""

    def __init__(
        self,
        piece_id: str,
        milestone_id: str,
        move: chess.Move,
        offered_square: chess.Square,
        offered_piece_type: chess.PieceType,
        offering_ply: int,
        material_captured_on_offer: int = 0,
    ):
        self.intent_id = str(uuid.uuid4())[:8]
        self.piece_id = piece_id
        self.milestone_id = milestone_id
        self.move = move
        self.offered_square = offered_square
        self.offered_piece_type = offered_piece_type
        self.offering_ply = offering_ply
        self.material_captured_on_offer = material_captured_on_offer

    @property
    def target_square(self) -> chess.Square:
        return self.offered_square

    @property
    def target_milestone_id(self) -> str:
        return self.milestone_id

    @property
    def expected_sacrifice_type(self) -> str:
        return chess.piece_name(self.offered_piece_type)


class SacrificeEvent:
    """Recorded sacrifice event when opponent captures an intentionally offered piece."""

    def __init__(
        self,
        piece_id: str,
        piece_type: chess.PieceType,
        color: chess.Color,
        milestone_id: Optional[str],
        offering_move: chess.Move,
        capturing_move: chess.Move,
        offering_ply: int,
        capturing_ply: int,
        material_sacrificed: int,
        is_genuine: bool,
        rejection_reason: Optional[str] = None,
        captured_by_piece_type: Optional[chess.PieceType] = None,
    ):
        self.piece_id = piece_id
        self.piece_type = piece_type
        self.color = color
        self.milestone_id = milestone_id
        self.offering_move = offering_move
        self.capturing_move = capturing_move
        self.offering_ply = offering_ply
        self.capturing_ply = capturing_ply
        self.material_sacrificed = material_sacrificed
        self.is_genuine = is_genuine
        self.rejection_reason = rejection_reason
        self.captured_by_piece_type = captured_by_piece_type

    def __repr__(self) -> str:
        return (
            f"<SacrificeEvent {self.piece_id} genuine={self.is_genuine} "
            f"mat_diff={self.material_sacrificed} reason={self.rejection_reason}>"
        )


class PieceTracker:
    """
    Maintains persistent identities for all pieces, tracks pawn promotion lineages,
    distinguishes surviving pawns vs original pawns, and validates genuine sacrifices
    against blunders and equal exchanges.
    """

    def __init__(self, initial_fen: Optional[str] = None):
        self.pieces: Dict[str, TrackedPiece] = {}
        self.square_to_piece_id: Dict[chess.Square, str] = {}
        self.confirmed_sacrifices: List[SacrificeEvent] = []
        self.pending_intents: List[SacrificeIntent] = []
        self.ply_counter: int = 0
        self.our_color: chess.Color = chess.WHITE

        # Snapshot of initial surviving pawns for "every surviving pawn" objective
        self._initial_surviving_pawns_count: Dict[chess.Color, int] = {
            chess.WHITE: 8,
            chess.BLACK: 8,
        }

        self._init_board_state(initial_fen or chess.STARTING_FEN)

    def _init_board_state(self, fen: str) -> None:
        board = chess.Board(fen)
        self.pieces.clear()
        self.square_to_piece_id.clear()
        self.confirmed_sacrifices.clear()
        self.pending_intents.clear()
        self.ply_counter = board.ply()

        # Deterministic IDs for standard starting position
        is_standard_start = (fen == chess.STARTING_FEN)

        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece is None:
                continue

            color_prefix = "w" if piece.color == chess.WHITE else "b"
            sq_name = chess.square_name(sq)

            if is_standard_start:
                sym = chess.piece_symbol(piece.piece_type).lower()
                piece_id = f"{color_prefix}_{sym}{sq_name}"
            else:
                sym = chess.piece_symbol(piece.piece_type).lower()
                piece_id = f"{color_prefix}_{sym}_{sq_name}"

            tracked = TrackedPiece(
                piece_id=piece_id,
                color=piece.color,
                piece_type=piece.piece_type,
                original_square=sq,
                current_square=sq,
                is_original=True,
                is_promoted=False,
            )
            self.pieces[piece_id] = tracked
            self.square_to_piece_id[sq] = piece_id

        # Update initial surviving pawn snapshot
        for c in (chess.WHITE, chess.BLACK):
            self._initial_surviving_pawns_count[c] = len(self.get_surviving_pawns(c))

    def set_our_color(self, color: chess.Color) -> None:
        self.our_color = color

    def get_piece(self, piece_id: str) -> Optional[TrackedPiece]:
        return self.pieces.get(piece_id)

    def get_piece_at(self, square: chess.Square) -> Optional[TrackedPiece]:
        piece_id = self.square_to_piece_id.get(square)
        if piece_id:
            return self.pieces.get(piece_id)
        return None

    def get_original_major_minor_pieces(self, color: chess.Color) -> List[TrackedPiece]:
        """
        Returns all original major and minor pieces (R, N, B, Q).
        The King is STRICTLY excluded.
        """
        return [
            p for p in self.pieces.values()
            if p.color == color and p.is_original and p.is_major_or_minor
        ]

    def get_original_pawns(self, color: chess.Color) -> List[TrackedPiece]:
        """Returns the pawns present at initialization."""
        return [
            p for p in self.pieces.values()
            if p.color == color and p.is_original and p.is_pawn
        ]

    def get_surviving_pawns(self, color: chess.Color) -> List[TrackedPiece]:
        """
        Returns original pawns currently alive and unpromoted on the board.
        """
        return [
            p for p in self.pieces.values()
            if p.color == color
            and p.is_pawn
            and not p.is_captured
            and not p.is_promoted
        ]

    def get_promoted_pieces(
        self, color: chess.Color, piece_type: Optional[chess.PieceType] = None
    ) -> List[TrackedPiece]:
        """Returns active pieces that were created via pawn promotion."""
        return [
            p for p in self.pieces.values()
            if p.color == color
            and p.is_promoted
            and not p.is_captured
            and (piece_type is None or p.piece_type == piece_type)
        ]

    def get_confirmed_sacrifices(self, color: chess.Color) -> List[SacrificeEvent]:
        """Returns all confirmed genuine sacrifice events for this color."""
        return [s for s in self.confirmed_sacrifices if s.color == color and s.is_genuine]

    def is_queen_sacrificed(self, color: chess.Color) -> bool:
        """Returns True if the original queen was sacrificed genuinely."""
        for s in self.confirmed_sacrifices:
            if s.color == color and s.is_genuine and s.piece_type == chess.QUEEN:
                return True
        return False

    def all_original_pieces_sacrificed(self, color: chess.Color) -> bool:
        """
        Checks whether all 7 original major/minor pieces have confirmed genuine sacrifices.
        King is strictly excluded.
        """
        original_pieces = self.get_original_major_minor_pieces(color)
        if not original_pieces:
            return False

        sacrificed_ids = {
            s.piece_id for s in self.confirmed_sacrifices
            if s.color == color and s.is_genuine
        }
        return all(p.piece_id in sacrificed_ids for p in original_pieces)

    def register_sacrifice_intent(
        self,
        piece_id: str,
        milestone_id: Optional[str] = None,
        move: Optional[chess.Move] = None,
        board: Optional[chess.Board] = None,
        target_square: Optional[chess.Square] = None,
        target_milestone_id: Optional[str] = None,
        intended_at_ply: Optional[int] = None,
        expected_sacrifice_type: Optional[str] = None,
    ) -> SacrificeIntent:
        """
        Tags a candidate move with deliberate sacrifice intent.
        Strictly excludes the KING.
        Supports both positional and keyword invocations.
        """
        piece = self.pieces.get(piece_id)
        if not piece:
            raise ValueError(f"Unknown piece_id: {piece_id}")

        if piece.is_king:
            raise ValueError("The King is strictly excluded from sacrifice objectives.")

        if piece.is_captured:
            raise ValueError(f"Cannot sacrifice captured piece: {piece_id}")

        eff_milestone_id = milestone_id or target_milestone_id or "milestone_sacrifice"
        eff_square = target_square if target_square is not None else (move.to_square if move else piece.current_square)

        # Check material captured by this offering move (if any)
        mat_captured = 0
        if board and move:
            captured_piece = board.piece_at(move.to_square)
            if captured_piece:
                mat_captured = PIECE_VALUES.get(captured_piece.piece_type, 0)

        intent = SacrificeIntent(
            piece_id=piece_id,
            milestone_id=eff_milestone_id,
            move=move if move else chess.Move.null(),
            offered_square=eff_square or chess.A1,
            offered_piece_type=piece.piece_type,
            offering_ply=intended_at_ply if intended_at_ply is not None else self.ply_counter,
            material_captured_on_offer=mat_captured,
        )
        self.pending_intents.append(intent)
        return intent

    def apply_move(
        self,
        move: chess.Move,
        board_before: chess.Board,
        is_our_move: bool,
        declared_intent: Optional[SacrificeIntent] = None,
    ) -> Tuple[Optional[TrackedPiece], Optional[TrackedPiece]]:
        """
        Applies a move to the piece tracker state.
        Synchronizes square positions, tracks captures, promotions, castling, and en passant.
        Validates genuine sacrifices on opponent response.
        Returns: (moved_piece, captured_piece)
        """
        self.ply_counter += 1
        moved_piece = self.get_piece_at(move.from_square)
        if not moved_piece:
            # Fallback for unexpected square misalignment
            return None, None

        captured_piece: Optional[TrackedPiece] = None

        # 1. Handle captures
        # Check normal capture or en passant
        is_en_passant = board_before.is_en_passant(move)
        if is_en_passant:
            # The captured pawn is on the same file, but the previous rank
            ep_captured_sq = (
                chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
            )
            captured_piece = self.get_piece_at(ep_captured_sq)
            if captured_piece:
                captured_piece.is_captured = True
                captured_piece.captured_at_ply = self.ply_counter
                captured_piece.captured_by_piece_type = moved_piece.piece_type
                captured_piece.captured_by_color = moved_piece.color
                captured_piece.current_square = None
                self.square_to_piece_id.pop(ep_captured_sq, None)
        else:
            captured_piece = self.get_piece_at(move.to_square)
            if captured_piece:
                captured_piece.is_captured = True
                captured_piece.captured_at_ply = self.ply_counter
                captured_piece.captured_by_piece_type = moved_piece.piece_type
                captured_piece.captured_by_color = moved_piece.color
                captured_piece.current_square = None
                self.square_to_piece_id.pop(move.to_square, None)

        # 2. Check sacrifice acceptance if opponent just made a capture
        if not is_our_move and captured_piece and captured_piece.color == self.our_color:
            self._evaluate_sacrifice_resolution(captured_piece, move)

        # 3. Handle Castling
        if moved_piece.is_king and abs(chess.square_file(move.to_square) - chess.square_file(move.from_square)) == 2:
            self._handle_castling_rook(move, moved_piece.color)

        # 4. Move the active piece
        self.square_to_piece_id.pop(move.from_square, None)
        moved_piece.current_square = move.to_square
        moved_piece.moves_count += 1
        self.square_to_piece_id[move.to_square] = moved_piece.piece_id

        # 5. Handle Promotion
        if move.promotion is not None:
            self._handle_promotion(moved_piece, move)

        # 6. If it was our move, store declared intent for opponent's response
        if is_our_move and declared_intent:
            if declared_intent not in self.pending_intents:
                self.pending_intents.append(declared_intent)
        elif not is_our_move:
            # Clear pending intents that were not accepted by opponent on this response
            self.pending_intents.clear()

        return moved_piece, captured_piece

    def _evaluate_sacrifice_resolution(
        self, captured_piece: TrackedPiece, opponent_move: chess.Move
    ) -> None:
        """
        Validates whether opponent's capture satisfies an intentional sacrifice.
        Distinguishes genuine sacrifice from blunders, forced losses, and equal exchanges.
        """
        # Find matching intent
        matching_intent: Optional[SacrificeIntent] = None
        for it in self.pending_intents:
            if it.piece_id == captured_piece.piece_id:
                matching_intent = it
                break

        if not matching_intent:
            # Blunder or forced loss: piece captured without pre-move sacrifice intent tag!
            return

        # Opponent captured our intentionally offered piece!
        # Check material exchange contract:
        offered_val = PIECE_VALUES.get(matching_intent.offered_piece_type, 0)
        captured_on_offer_val = matching_intent.material_captured_on_offer
        net_material_loss = offered_val - captured_on_offer_val

        # Rule: Genuine sacrifice requires giving up material for lesser or zero material.
        # Equal exchange (e.g. N for N -> net_material_loss = 0) is NOT a sacrifice.
        if net_material_loss <= 0:
            # Equal or favorable trade
            event = SacrificeEvent(
                piece_id=captured_piece.piece_id,
                piece_type=captured_piece.piece_type,
                color=captured_piece.color,
                milestone_id=matching_intent.milestone_id,
                offering_move=matching_intent.move,
                capturing_move=opponent_move,
                offering_ply=matching_intent.offering_ply,
                capturing_ply=self.ply_counter,
                material_sacrificed=net_material_loss,
                is_genuine=False,
                rejection_reason="equal_exchange",
                captured_by_piece_type=None,
            )
            self.confirmed_sacrifices.append(event)
            return

        # Verified genuine sacrifice!
        event = SacrificeEvent(
            piece_id=captured_piece.piece_id,
            piece_type=captured_piece.piece_type,
            color=captured_piece.color,
            milestone_id=matching_intent.milestone_id,
            offering_move=matching_intent.move,
            capturing_move=opponent_move,
            offering_ply=matching_intent.offering_ply,
            capturing_ply=self.ply_counter,
            material_sacrificed=net_material_loss,
            is_genuine=True,
            rejection_reason=None,
            captured_by_piece_type=None,
        )
        self.confirmed_sacrifices.append(event)

    def _handle_castling_rook(self, king_move: chess.Move, color: chess.Color) -> None:
        rank = 0 if color == chess.WHITE else 7
        if chess.square_file(king_move.to_square) == 6:  # Kingside (g-file)
            rook_from = chess.square(7, rank)  # h1 / h8
            rook_to = chess.square(5, rank)    # f1 / f8
        else:  # Queenside (c-file)
            rook_from = chess.square(0, rank)  # a1 / a8
            rook_to = chess.square(3, rank)    # d1 / d8

        rook_piece = self.get_piece_at(rook_from)
        if rook_piece:
            self.square_to_piece_id.pop(rook_from, None)
            rook_piece.current_square = rook_to
            rook_piece.moves_count += 1
            self.square_to_piece_id[rook_to] = rook_piece.piece_id

    def _handle_promotion(self, pawn_piece: TrackedPiece, move: chess.Move) -> TrackedPiece:
        assert move.promotion is not None
        # Mark originating pawn as promoted
        pawn_piece.is_promoted = True
        pawn_piece.current_square = None
        self.square_to_piece_id.pop(move.to_square, None)

        promoted_sym = chess.piece_symbol(move.promotion).lower()
        new_piece_id = f"prom_{pawn_piece.piece_id}_{promoted_sym}_{self.ply_counter}"

        new_piece = TrackedPiece(
            piece_id=new_piece_id,
            color=pawn_piece.color,
            piece_type=move.promotion,
            original_square=pawn_piece.original_square,
            current_square=move.to_square,
            is_original=False,
            is_promoted=True,
            promoted_from_id=pawn_piece.piece_id,
            promoted_at_ply=self.ply_counter,
        )
        self.pieces[new_piece_id] = new_piece
        self.square_to_piece_id[move.to_square] = new_piece_id
        return new_piece

    def clone(self) -> "PieceTracker":
        """Creates an independent deep-copy for search and tree simulations."""
        new_tracker = PieceTracker.__new__(PieceTracker)
        new_tracker.pieces = {pid: p.clone() for pid, p in self.pieces.items()}
        new_tracker.square_to_piece_id = dict(self.square_to_piece_id)
        new_tracker.confirmed_sacrifices = list(self.confirmed_sacrifices)
        new_tracker.pending_intents = list(self.pending_intents)
        new_tracker.ply_counter = self.ply_counter
        new_tracker.our_color = self.our_color
        new_tracker._initial_surviving_pawns_count = dict(self._initial_surviving_pawns_count)
        return new_tracker
