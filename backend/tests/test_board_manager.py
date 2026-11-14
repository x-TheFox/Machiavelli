"""Unit tests for BoardManager."""

import pytest
import chess
from backend.app.chess_engine.board_manager import BoardManager, IllegalMoveError


def test_board_manager_initialization():
    bm = BoardManager()
    assert bm.fen == chess.STARTING_FEN
    assert bm.turn == chess.WHITE
    assert bm.turn_name == "white"
    assert bm.fullmove_number == 1
    assert bm.halfmove_clock == 0
    assert bm.ply == 0
    assert not bm.is_game_over()
    assert not bm.is_check()
    assert len(bm.legal_moves) == 20


def test_custom_fen_initialization():
    # Endgame FEN
    fen = "8/8/8/4k3/8/8/4K3/4Q3 w - - 0 1"
    bm = BoardManager(fen=fen)
    assert bm.turn == chess.WHITE
    assert bm.piece_at("e1").piece_type == chess.QUEEN
    assert bm.piece_at(chess.E2).piece_type == chess.KING
    assert bm.king_square(chess.BLACK) == chess.E5


def test_move_execution_and_pop():
    bm = BoardManager()
    # Execute e2e4
    m1 = bm.push_uci("e2e4")
    assert m1.uci() == "e2e4"
    assert bm.turn == chess.BLACK
    assert bm.ply == 1

    # Execute e7e5 via SAN
    m2 = bm.push_san("e5")
    assert m2.uci() == "e7e5"
    assert bm.turn == chess.WHITE
    assert bm.ply == 2

    # Pop moves
    popped = bm.pop()
    assert popped.uci() == "e7e5"
    assert bm.ply == 1
    assert bm.turn == chess.BLACK


def test_illegal_move_rejection():
    bm = BoardManager()
    with pytest.raises(IllegalMoveError):
        bm.push_uci("e2e5")  # Pawn can't jump 3 squares

    with pytest.raises(IllegalMoveError):
        bm.push_san("Qxf7")  # Queen can't take f7 on move 1


def test_conversions():
    bm = BoardManager()
    assert bm.uci_to_san("g1f3") == "Nf3"
    assert bm.san_to_uci("Nf3") == "g1f3"

    m = bm.parse_move("e4")
    assert m.uci() == "e2e4"
    m_uci = bm.parse_move("e2e4")
    assert m_uci == m


def test_checkmate_and_terminal_checks():
    # Fool's Mate: 1. f3 e5 2. g4 Qh4#
    bm = BoardManager()
    bm.push_san("f3")
    bm.push_san("e5")
    bm.push_san("g4")
    bm.push_san("Qh4#")

    assert bm.is_check()
    assert bm.is_checkmate()
    assert bm.is_game_over()
    assert bm.outcome().winner == chess.BLACK
    assert bm.result() == "0-1"
    assert bm.termination_reason() == "checkmate"


def test_stalemate_detection():
    # Stalemate position
    fen = "k7/8/1Q6/8/8/8/8/7K b - - 0 1"
    bm = BoardManager(fen=fen)
    assert not bm.is_check()
    assert bm.is_stalemate()
    assert bm.is_game_over()
    assert bm.result() == "1/2-1/2"
    assert bm.termination_reason() == "stalemate"


def test_insufficient_material():
    # King vs King
    bm = BoardManager(fen="8/8/8/4k3/8/8/4K3/8 w - - 0 1")
    assert bm.is_insufficient_material()
    assert bm.is_game_over()


def test_piece_and_attack_inspection():
    bm = BoardManager()
    # e4 attacked by no one initially
    assert not bm.is_attacked_by(chess.WHITE, "e4")
    assert not bm.is_attacked_by(chess.BLACK, "e4")

    # e2 is attacked by white queen, king, bishop, knight
    assert bm.is_attacked_by(chess.WHITE, "e2")
    attackers = bm.attackers(chess.WHITE, "e2")
    assert len(attackers) >= 3

    white_knights = bm.pieces(chess.KNIGHT, chess.WHITE)
    assert len(white_knights) == 2
    assert chess.B1 in white_knights
    assert chess.G1 in white_knights


def test_history_and_cloning():
    bm = BoardManager()
    bm.push_san("e4")
    bm.push_san("c5")
    bm.push_san("Nf3")

    assert bm.san_history() == ["e4", "c5", "Nf3"]
    assert bm.uci_history() == ["e2e4", "c7c5", "g1f3"]

    clone = bm.copy()
    assert clone.fen == bm.fen
    assert clone.san_history() == bm.san_history()

    # Mutating clone does not affect original
    clone.push_san("d6")
    assert clone.ply == 4
    assert bm.ply == 3
