"""Board Manager.

Encapsulates python-chess Board state, providing:
- Board initialization and FEN manipulation
- Strict legal move parsing, validation, and execution (UCI, SAN, Move objects)
- Move conversions (UCI <-> SAN <-> chess.Move)
- Full terminal condition checks (Checkmate, Stalemate, Insufficient Material, 50/75 moves, Repetition)
- Piece and square inspection helpers (attackers, piece sets, captures, promotions)
- Move history tracking and state cloning
"""

from typing import List, Optional, Sequence, Set, Tuple, Union
import chess


class IllegalMoveError(ValueError):
    """Raised when an illegal or unparseable move is attempted."""
    pass


class BoardManager:
    """Wrapper around python-chess Board with high-level game management utilities."""

    def __init__(self, fen: Optional[str] = None, chess960: bool = False):
        if fen:
            self._board = chess.Board(fen=fen, chess960=chess960)
        else:
            self._board = chess.Board(chess960=chess960)

    @property
    def board(self) -> chess.Board:
        """Underlying python-chess Board object."""
        return self._board

    @property
    def fen(self) -> str:
        """Current FEN string."""
        return self._board.fen()

    @property
    def turn(self) -> chess.Color:
        """chess.WHITE (True) or chess.BLACK (False)."""
        return self._board.turn

    @property
    def turn_name(self) -> str:
        """'white' or 'black'."""
        return "white" if self._board.turn == chess.WHITE else "black"

    @property
    def fullmove_number(self) -> int:
        return self._board.fullmove_number

    @property
    def halfmove_clock(self) -> int:
        return self._board.halfmove_clock

    @property
    def ply(self) -> int:
        """Total half-moves played from initial position."""
        return len(self._board.move_stack)

    @property
    def legal_moves(self) -> List[chess.Move]:
        """List of all legal moves in current position."""
        return list(self._board.legal_moves)

    @property
    def legal_moves_uci(self) -> List[str]:
        """List of legal moves in UCI format."""
        return [m.uci() for m in self._board.legal_moves]

    @property
    def legal_moves_san(self) -> List[str]:
        """List of legal moves in SAN format."""
        return [self._board.san(m) for m in self._board.legal_moves]

    def is_legal(self, move: Union[chess.Move, str]) -> bool:
        """Check if a Move, UCI string, or SAN string is legal in current position."""
        try:
            m = self.parse_move(move) if isinstance(move, str) else move
            return m in self._board.legal_moves
        except (ValueError, IllegalMoveError):
            return False

    def parse_move(self, move_str: str) -> chess.Move:
        """Parses a move string given in either UCI (e.g. 'e2e4') or SAN (e.g. 'Nf3') format."""
        cleaned = move_str.strip()
        # Try parsing as UCI first
        try:
            m = chess.Move.from_uci(cleaned)
            if m in self._board.legal_moves:
                return m
        except ValueError:
            pass

        # Try parsing as SAN
        try:
            return self._board.parse_san(cleaned)
        except ValueError:
            pass

        # If move was UCI syntax but not legal, try again to confirm legality error
        try:
            m = chess.Move.from_uci(cleaned)
            raise IllegalMoveError(f"Move '{cleaned}' is illegal in current position: {self.fen}")
        except ValueError:
            raise IllegalMoveError(f"Move '{cleaned}' could not be parsed as UCI or SAN in position: {self.fen}")

    def push(self, move: chess.Move) -> chess.Move:
        """Executes a chess.Move on the board after validating legality."""
        if move not in self._board.legal_moves:
            raise IllegalMoveError(f"Illegal move {move.uci()} in position: {self.fen}")
        self._board.push(move)
        return move

    def push_uci(self, uci_str: str) -> chess.Move:
        """Parses and executes a move in UCI format (e.g. 'e2e4', 'e7e8q')."""
        try:
            move = chess.Move.from_uci(uci_str.strip())
        except ValueError as e:
            raise IllegalMoveError(f"Invalid UCI syntax '{uci_str}': {e}") from e

        if move not in self._board.legal_moves:
            raise IllegalMoveError(f"Illegal move '{uci_str}' in position: {self.fen}")

        self._board.push(move)
        return move

    def push_san(self, san_str: str) -> chess.Move:
        """Parses and executes a move in SAN format (e.g. 'Nf3', 'O-O', 'exd8=N#')."""
        try:
            move = self._board.parse_san(san_str.strip())
        except ValueError as e:
            raise IllegalMoveError(f"Invalid or illegal SAN move '{san_str}': {e}") from e

        self._board.push(move)
        return move

    def pop(self) -> chess.Move:
        """Undoes the last move played on the board."""
        return self._board.pop()

    def uci_to_san(self, uci_str: str) -> str:
        """Converts a UCI move string to SAN representation in current position."""
        move = chess.Move.from_uci(uci_str.strip())
        if move not in self._board.legal_moves:
            raise IllegalMoveError(f"Move '{uci_str}' is illegal in position: {self.fen}")
        return self._board.san(move)

    def san_to_uci(self, san_str: str) -> str:
        """Converts a SAN move string to UCI format in current position."""
        move = self._board.parse_san(san_str.strip())
        return move.uci()

    def move_to_san(self, move: chess.Move) -> str:
        """Converts a chess.Move to SAN."""
        return self._board.san(move)

    def move_to_uci(self, move: chess.Move) -> str:
        """Converts a chess.Move to UCI."""
        return move.uci()

    # --- Terminal & Game Status Checks ---

    def is_game_over(self, claim_draw: bool = False) -> bool:
        """Determines if the game is over."""
        return self._board.is_game_over(claim_draw=claim_draw)

    def is_check(self) -> bool:
        """Returns True if the side to move is currently in check."""
        return self._board.is_check()

    def is_checkmate(self) -> bool:
        """Returns True if the current position is checkmate."""
        return self._board.is_checkmate()

    def is_stalemate(self) -> bool:
        """Returns True if the current position is stalemate."""
        return self._board.is_stalemate()

    def is_insufficient_material(self) -> bool:
        """Returns True if neither side has sufficient material to mate."""
        return self._board.is_insufficient_material()

    def is_seventyfive_moves(self) -> bool:
        """Returns True if 75 moves have passed without a capture or pawn move."""
        return self._board.is_seventyfive_moves()

    def is_fivefold_repetition(self) -> bool:
        """Returns True if identical position has occurred 5 times."""
        return self._board.is_fivefold_repetition()

    def can_claim_draw(self) -> bool:
        """Returns True if a draw can be claimed under 50-move rule or 3-fold repetition."""
        return self._board.can_claim_draw()

    def can_claim_fifty_moves(self) -> bool:
        return self._board.can_claim_fifty_moves()

    def can_claim_threefold_repetition(self) -> bool:
        return self._board.can_claim_threefold_repetition()

    def outcome(self, claim_draw: bool = False) -> Optional[chess.Outcome]:
        """Returns chess.Outcome if the game is finished, else None."""
        return self._board.outcome(claim_draw=claim_draw)

    def result(self, claim_draw: bool = False) -> str:
        """Returns '1-0', '0-1', '1/2-1/2', or '*'."""
        out = self.outcome(claim_draw=claim_draw)
        if out is None:
            return "*"
        return out.result()

    def termination_reason(self, claim_draw: bool = False) -> Optional[str]:
        """Returns plain string explaining termination cause, or None."""
        out = self.outcome(claim_draw=claim_draw)
        if out is None:
            return None
        return out.termination.name.lower()

    # --- Piece & Board Inspection ---

    def _resolve_square(self, sq: Union[str, int]) -> int:
        if isinstance(sq, str):
            return chess.parse_square(sq.lower())
        return sq

    def piece_at(self, square: Union[str, int]) -> Optional[chess.Piece]:
        return self._board.piece_at(self._resolve_square(square))

    def piece_type_at(self, square: Union[str, int]) -> Optional[chess.PieceType]:
        piece = self.piece_at(square)
        return piece.piece_type if piece else None

    def color_at(self, square: Union[str, int]) -> Optional[chess.Color]:
        piece = self.piece_at(square)
        return piece.color if piece else None

    def pieces(self, piece_type: chess.PieceType, color: chess.Color) -> chess.SquareSet:
        """Returns bitboard SquareSet of squares occupied by given piece type and color."""
        return self._board.pieces(piece_type, color)

    def get_pieces(
        self,
        color: Optional[chess.Color] = None,
        piece_type: Optional[chess.PieceType] = None,
    ) -> List[Tuple[int, chess.Piece]]:
        """Returns a list of (square_index, piece) tuples matching color/piece_type filters."""
        result: List[Tuple[int, chess.Piece]] = []
        for sq in chess.SQUARES:
            p = self._board.piece_at(sq)
            if p is not None:
                if color is not None and p.color != color:
                    continue
                if piece_type is not None and p.piece_type != piece_type:
                    continue
                result.append((sq, p))
        return result

    def attackers(self, color: chess.Color, square: Union[str, int]) -> chess.SquareSet:
        """Returns SquareSet of squares occupied by pieces of `color` attacking `square`."""
        return self._board.attackers(color, self._resolve_square(square))

    def is_attacked_by(self, color: chess.Color, square: Union[str, int]) -> bool:
        """Returns True if `square` is attacked by any piece of `color`."""
        return self._board.is_attacked_by(color, self._resolve_square(square))

    def king_square(self, color: chess.Color) -> Optional[int]:
        """Returns square index of the king of given color."""
        return self._board.king(color)

    def is_capture(self, move: chess.Move) -> bool:
        """Checks if a move is a capture (including en-passant)."""
        return self._board.is_capture(move)

    def is_en_passant(self, move: chess.Move) -> bool:
        return self._board.is_en_passant(move)

    def is_castling(self, move: chess.Move) -> bool:
        return self._board.is_castling(move)

    def is_promotion(self, move: chess.Move) -> bool:
        return move.promotion is not None

    def san_history(self) -> List[str]:
        """Reconstructs the full game move history in SAN."""
        temp = chess.Board()
        sans = []
        for m in self._board.move_stack:
            sans.append(temp.san(m))
            temp.push(m)
        return sans

    def uci_history(self) -> List[str]:
        """Returns list of all moves played in UCI string format."""
        return [m.uci() for m in self._board.move_stack]

    def copy(self) -> "BoardManager":
        """Creates an independent deep copy of this BoardManager."""
        new_mgr = BoardManager()
        new_mgr._board = self._board.copy(stack=True)
        return new_mgr

    def reset(self) -> None:
        """Resets board to initial standard chess position."""
        self._board.reset()

    def set_fen(self, fen: str) -> None:
        """Sets board to a specified FEN position."""
        self._board.set_fen(fen)

    def __str__(self) -> str:
        return str(self._board)

    def __repr__(self) -> str:
        return f"<BoardManager fen='{self.fen}'>"
