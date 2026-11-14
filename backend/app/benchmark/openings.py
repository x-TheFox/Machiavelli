"""Standard ECO Openings Repertoire for Machiavelli Benchmarking.

Contains 15 diverse standard opening book definitions across classical ECO categories
(Open, Semi-Open, Closed, Flank, and Indian Defenses) used for fair-play balanced
White/Black benchmarking matches.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import chess


@dataclass(frozen=True)
class Opening:
    """Represents a standard opening book entry."""
    eco: str
    name: str
    category: str
    moves_san: List[str]
    moves_uci: List[str] = field(default_factory=list)
    fen: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "eco": self.eco,
            "name": self.name,
            "category": self.category,
            "moves_san": list(self.moves_san),
            "moves_uci": list(self.moves_uci),
            "fen": self.fen,
            "ply_count": len(self.moves_san),
        }

    def create_board(self) -> chess.Board:
        """Create a new chess.Board with the opening moves applied."""
        board = chess.Board()
        for uci in self.moves_uci:
            board.push(chess.Move.from_uci(uci))
        return board


def _build_opening(eco: str, name: str, category: str, moves_san: List[str]) -> Opening:
    """Helper to construct an Opening, calculating UCI moves and resulting FEN."""
    board = chess.Board()
    moves_uci: List[str] = []
    for san in moves_san:
        move = board.parse_san(san)
        moves_uci.append(move.uci())
        board.push(move)
    return Opening(
        eco=eco,
        name=name,
        category=category,
        moves_san=moves_san,
        moves_uci=moves_uci,
        fen=board.fen(),
    )


# 15 Standard diverse ECO openings (balanced across Open, Semi-Open, Closed, Flank, Indian)
OPENINGS_CATALOG: List[Opening] = [
    _build_opening(
        eco="B90",
        name="Sicilian Defence (Najdorf Variation)",
        category="Semi-Open Games",
        moves_san=["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"],
    ),
    _build_opening(
        eco="C18",
        name="French Defence (Winawer Variation)",
        category="Semi-Open Games",
        moves_san=["e4", "e6", "d4", "d5", "Nc3", "Bb4", "e5", "c5", "a3", "Bxc3+", "bxc3", "Ne7"],
    ),
    _build_opening(
        eco="C84",
        name="Ruy Lopez (Closed / Morphy Defence)",
        category="Open Games",
        moves_san=["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Ba4", "Nf6", "O-O", "Be7", "Re1", "b5", "Bb3", "d6"],
    ),
    _build_opening(
        eco="B18",
        name="Caro-Kann Defence (Classical Variation)",
        category="Semi-Open Games",
        moves_san=["e4", "c6", "d4", "d5", "Nc3", "dxe4", "Nxe4", "Bf5", "Ng3", "Bg6"],
    ),
    _build_opening(
        eco="C50",
        name="Italian Game (Giuoco Piano)",
        category="Open Games",
        moves_san=["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "d3", "Nf6", "O-O", "d6"],
    ),
    _build_opening(
        eco="D37",
        name="Queen's Gambit Declined (Orthodox Variation)",
        category="Closed Games",
        moves_san=["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Nf3", "Be7", "Bf4", "O-O"],
    ),
    _build_opening(
        eco="D20",
        name="Queen's Gambit Accepted",
        category="Closed Games",
        moves_san=["d4", "d5", "c4", "dxc4", "Nf3", "Nf6", "e3", "e6", "Bxc4", "c5"],
    ),
    _build_opening(
        eco="E92",
        name="King's Indian Defence (Classical)",
        category="Indian Defences",
        moves_san=["d4", "Nf6", "c4", "g6", "Nc3", "Bg7", "e4", "d6", "Nf3", "O-O", "Be2", "e5"],
    ),
    _build_opening(
        eco="E32",
        name="Nimzo-Indian Defence (Classical)",
        category="Indian Defences",
        moves_san=["d4", "Nf6", "c4", "e6", "Nc3", "Bb4", "Qc2", "O-O", "a3", "Bxc3+", "Qxc3", "b6"],
    ),
    _build_opening(
        eco="D85",
        name="Grünfeld Defence (Exchange Variation)",
        category="Indian Defences",
        moves_san=["d4", "Nf6", "c4", "g6", "Nc3", "d5", "cxd5", "Nxd5", "e4", "Nxc3", "bxc3", "Bg7"],
    ),
    _build_opening(
        eco="A28",
        name="English Opening (Four Knights)",
        category="Flank Openings",
        moves_san=["c4", "e5", "Nc3", "Nf6", "Nf3", "Nc6", "e3", "Bb4"],
    ),
    _build_opening(
        eco="A09",
        name="Réti Opening",
        category="Flank Openings",
        moves_san=["Nf3", "d5", "c4", "d4", "g3", "c5", "Bg2", "Nc6"],
    ),
    _build_opening(
        eco="B01",
        name="Scandinavian Defence (Modern Variation)",
        category="Semi-Open Games",
        moves_san=["e4", "d5", "exd5", "Nf6", "d4", "Nxd5", "Nf3", "g6"],
    ),
    _build_opening(
        eco="A88",
        name="Dutch Defence (Leningrad Variation)",
        category="Flank Openings",
        moves_san=["d4", "f5", "g3", "Nf6", "Bg2", "g6", "Nf3", "Bg7", "O-O", "O-O", "c4", "d6", "Nc3", "c6"],
    ),
    _build_opening(
        eco="D11",
        name="Slav Defence (Modern Line)",
        category="Closed Games",
        moves_san=["d4", "d5", "c4", "c6", "Nf3", "Nf6", "e3", "Bf5", "Nc3", "e6"],
    ),
]


def get_openings() -> List[Opening]:
    """Return the complete list of 15 standard openings."""
    return list(OPENINGS_CATALOG)


def get_opening_by_eco(eco: str) -> Optional[Opening]:
    """Find opening by ECO code."""
    for op in OPENINGS_CATALOG:
        if op.eco.upper() == eco.upper():
            return op
    return None


def get_opening_by_name(name: str) -> Optional[Opening]:
    """Find opening by partial or full name."""
    needle = name.lower()
    for op in OPENINGS_CATALOG:
        if needle in op.name.lower():
            return op
    return None


def create_board_from_opening(opening: Opening) -> chess.Board:
    """Create a chess.Board initialized with the moves of an opening."""
    return opening.create_board()
