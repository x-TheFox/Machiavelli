import chess
import pytest

from backend.app.chess_engine.feasibility import FeasibilityEngine
from backend.app.chess_engine.goal_interpreter import GoalInterpreter
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import PieceTracker


def test_search_timeout_never_proven_impossible():
    """
    CRITICAL CONTRACT:
    A search timeout must NEVER be interpreted as impossibility. It must remain UNRESOLVED.
    """
    board = chess.Board()
    tracker = PieceTracker()
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective(
        "Sacrifice all original pieces, promote every surviving pawn into a knight, and checkmate using the promoted knights"
    )

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report = engine.evaluate(board, goal, tracker, is_search_timeout=True)

    assert report.status == FeasibilityStatus.UNRESOLVED
    assert "UNRESOLVED" in report.reason
    assert report.status != FeasibilityStatus.PROVEN_IMPOSSIBLE


def test_terminal_checkmate_against_us_is_proven_impossible():
    # Fool's mate: 1. f3 e5 2. g4 Qh4# (White is checkmated)
    board = chess.Board()
    board.push_san("f3")
    board.push_san("e5")
    board.push_san("g4")
    board.push_san("Qh4#")
    assert board.is_checkmate() and board.turn == chess.WHITE

    tracker = PieceTracker(board.fen())
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Win the game in under 30 moves")

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report = engine.evaluate(board, goal, tracker)

    assert report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "King is checkmated" in report.reason


def test_stalemate_is_proven_impossible():
    # Stalemate position
    fen = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    # Black is stalemated
    board = chess.Board(fen)
    assert board.is_stalemate()

    tracker = PieceTracker(fen)
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Checkmate with a rook", color="black")

    engine = FeasibilityEngine(our_color=chess.BLACK)
    report = engine.evaluate(board, goal, tracker)

    assert report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "stalemate" in report.reason.lower()


def test_zero_captures_invariant_violation():
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Win without capturing any pieces", color="white")

    engine = FeasibilityEngine(our_color=chess.WHITE)

    # Initial state is feasible
    report1 = engine.evaluate(board, goal, tracker)
    assert report1.status == FeasibilityStatus.FEASIBLE

    # Simulate White capturing a Black piece
    # Suppose Black pawn was captured by White
    black_pawn = tracker.get_piece_at(chess.E5)
    assert black_pawn is not None
    black_pawn.is_captured = True
    black_pawn.captured_by_color = chess.WHITE

    report2 = engine.evaluate(board, goal, tracker)
    assert report2.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "Capture limit exceeded" in report2.reason


def test_no_pawn_loss_invariant_violation():
    fen = chess.STARTING_FEN
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Promote all 8 pawns to queens", color="white")

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report1 = engine.evaluate(board, goal, tracker)
    assert report1.status == FeasibilityStatus.FEASIBLE

    # Capture one White original pawn
    pawn_a2 = tracker.get_piece_at(chess.A2)
    assert pawn_a2 is not None
    pawn_a2.is_captured = True

    report2 = engine.evaluate(board, goal, tracker)
    assert report2.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "no_pawn_losses" in report2.reason or "captured" in report2.reason


def test_original_piece_lost_without_sacrifice_proof():
    # Goal: Sacrifice all original pieces
    fen = chess.STARTING_FEN
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective(
        "Sacrifice all original pieces, promote every surviving pawn into a knight, and checkmate using the promoted knights",
        color="white",
    )

    engine = FeasibilityEngine(our_color=chess.WHITE)
    assert engine.evaluate(board, goal, tracker).status == FeasibilityStatus.FEASIBLE

    # White original knight on b1 is captured as an unforced blunder (no genuine sacrifice)
    knight_b1 = tracker.get_piece_at(chess.B1)
    assert knight_b1 is not None
    knight_b1.is_captured = True
    # tracker.confirmed_sacrifices remains empty!

    report = engine.evaluate(board, goal, tracker)
    assert report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "lost without genuine sacrifice" in report.reason


def test_surviving_pawns_eliminated_proof():
    # Goal: Promote surviving pawns
    # Position with non-insufficient material (e.g. queens on board) so insufficient material doesn't trigger
    fen = "6qk/8/8/8/8/8/8/KQ6 w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Promote all surviving pawns to knights", color="white")
    goal.milestones[0].target_count = 1  # 1 was required

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report = engine.evaluate(board, goal, tracker)
    assert report.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "surviving pawn" in report.reason.lower() or "pawns" in report.reason.lower()


def test_threat_detection_at_risk():
    # Setup position where White pawn on e4 is attacked by Black knight on d6 and undefended
    fen = "7k/8/3n4/8/4P3/8/8/7K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Promote all surviving pawns to knights", color="white")

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report = engine.evaluate(board, goal, tracker)

    assert report.status == FeasibilityStatus.AT_RISK
    assert len(report.threatened_entities) > 0
    assert "tactical threats detected" in report.reason.lower()


def test_goal_completed_detection():
    # Setup position where White delivers smothered checkmate with a knight
    fen = "6rk/6pp/8/4N3/8/8/8/7K w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    # Deliver checkmate: Nf7#
    mate_move = chess.Move.from_uci("e5f7")
    board.push(mate_move)
    assert board.is_checkmate()

    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Checkmate with a knight", color="white")
    goal.milestones[0].status = MilestoneStatus.COMPLETED

    engine = FeasibilityEngine(our_color=chess.WHITE)
    report = engine.evaluate(board, goal, tracker)

    assert report.status == FeasibilityStatus.COMPLETED
    assert "verified" in report.reason.lower()
