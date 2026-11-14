"""Section 11 Main Promotional Objective Integration Test Suite.

Validates the master Machiavelli objective:
"Win by sacrificing all original pieces, promoting every surviving pawn into a knight,
and delivering checkmate using the promoted knights."

Covers:
- Tier 1: Deterministic Controlled Positions (Genuine sacrifices, Promoted Knight lineage, Checkmate delivery)
- Tier 1: King Exclusion Invariant (King can NEVER be sacrificed)
- Tier 1: Genuine Sacrifice vs Blunder / Equal Exchange Contract
- Tier 1: Surviving Pawns vs All 8 Original Pawns semantics
- Tier 1: Impossibility Engine Contract (Timeout != Impossible)
- Tier 2: Live Engine Match Execution with Calibrated Stockfish Opponent
- Tier 3: 15 ECO Openings Repertoire & Benchmark Exporters
"""

import os
import sys
import pytest
import chess

# Ensure backend and root paths are available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.chess_engine.piece_tracker import PieceTracker, TrackedPiece
from app.chess_engine.goal_schema import (
    FeasibilityStatus,
    MilestoneStatus,
    MilestoneType,
    Invariant,
    Milestone,
    GoalDefinition,
)
from app.chess_engine.goal_interpreter import GoalInterpreter
from app.chess_engine.feasibility import FeasibilityEngine
from app.benchmark.openings import get_openings, get_opening_by_eco
from app.benchmark.metrics import (
    GameMetric,
    TournamentSummary,
    compute_tournament_summary,
    export_to_json,
    export_to_csv,
    export_to_pgn,
    generate_markdown_report,
)
from app.benchmark.tournament import TournamentConfig, TournamentRunner


# =====================================================================
# TIER 1: DETERMINISTIC INTEGRATION TESTS (Controlled Legal Positions)
# =====================================================================

def test_tier1_section11_deterministic_grand_challenge():
    """
    Tier 1 Deterministic Verification of the Section 11 Grand Challenge:
    Position: 6br/5P1k/5K1p/q7/8/8/8/3R4 w - - 0 1
    
    1. White has:
       - King on f6 (safe, excluded from sacrifice)
       - Original Rook on d1 (last surviving original major/minor piece)
       - Surviving Pawn on f7 (the only surviving pawn)
    2. Black has:
       - King on h7, Bishop on g8, Rook on h8, Pawn on h6, Queen on a5
    
    Sequence:
    - Move 1: White registers intent and sacrifices original Rook: 1. Rd5!
    - Move 1...: Black captures with Queen: 1... Qxd5
      -> Genuine sacrifice confirmed (Rook offered on attacked square, accepted by Queen, mat diff = 5).
      -> All original pieces sacrificed! Milestone 1 Completed.
    - Move 2: White promotes surviving pawn: 2. f7-f8=N#
      -> Pawn promotes to Knight.
      -> Surviving pawns = 0, Promoted knights = 1.
      -> Lineage links back to originating pawn 'w_p_f7'.
      -> Milestone 2 Completed.
      -> Checkmate delivered by the promoted knight!
      -> Milestone 3 Completed.
      -> Full Goal DAG transitions to COMPLETED.
    """
    fen = "6br/5P1k/5K1p/q7/8/8/8/3R4 w - - 0 1"
    board = chess.Board(fen)
    assert board.is_valid(), "Position must be legal"
    assert not board.is_check(), "Position must not start in check"

    # Initialize PieceTracker
    tracker = PieceTracker(fen)
    tracker.set_our_color(chess.WHITE)

    # Initial state verification
    orig_pieces = tracker.get_original_major_minor_pieces(chess.WHITE)
    assert len(orig_pieces) == 1
    assert orig_pieces[0].piece_type == chess.ROOK
    assert orig_pieces[0].current_square == chess.D1

    surviving_pawns = tracker.get_surviving_pawns(chess.WHITE)
    assert len(surviving_pawns) == 1
    assert surviving_pawns[0].current_square == chess.F7

    # Compile Section 11 Goal
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective(
        "Sacrifice all original pieces, promote every surviving pawn into a knight, and checkmate using the promoted knights",
        color="white",
        force_deterministic=True,
    )
    assert len(goal.milestones) == 3
    m1 = goal.get_milestone("m1_sacrifice_original_pieces")
    m2 = goal.get_milestone("m2_promote_surviving_pawns")
    m3 = goal.get_milestone("m3_checkmate_promoted_knights")
    assert m1 and m2 and m3
    m1.target_count = 1  # 1 original piece in this controlled position

    feasibility_engine = FeasibilityEngine(our_color=chess.WHITE)
    assert goal.feasibility_status == FeasibilityStatus.FEASIBLE

    # -------------------------------------------------------------
    # Step 1: Deliberate Sacrifice of Original Rook (Rd5)
    # -------------------------------------------------------------
    m_rd5 = chess.Move.from_uci("d1d5")
    assert m_rd5 in board.legal_moves

    rook_piece = tracker.get_piece_at(chess.D1)
    assert rook_piece is not None
    intent = tracker.register_sacrifice_intent(
        piece_id=rook_piece.piece_id,
        milestone_id=m1.id,
        move=m_rd5,
        board=board,
    )
    assert intent.offered_square == chess.D5

    board_before = board.copy()
    board.push(m_rd5)
    tracker.apply_move(m_rd5, board_before, is_our_move=True, declared_intent=intent)

    # Step 1... Opponent captures on d5 with Queen (Qxd5)
    m_qxd5 = chess.Move.from_uci("a5d5")
    assert m_qxd5 in board.legal_moves

    board_before = board.copy()
    board.push(m_qxd5)
    tracker.apply_move(m_qxd5, board_before, is_our_move=False)

    # Verify sacrifice was confirmed as genuine
    sacs = tracker.get_confirmed_sacrifices(chess.WHITE)
    assert len(sacs) == 1
    assert sacs[0].is_genuine is True
    assert sacs[0].material_sacrificed == 5
    assert sacs[0].piece_type == chess.ROOK
    assert rook_piece.is_captured is True

    # Advance Milestone 1
    assert tracker.all_original_pieces_sacrificed(chess.WHITE) is True
    m1.status = MilestoneStatus.COMPLETED
    goal.advance_dag()
    assert m2.status == MilestoneStatus.ACTIVE
    assert goal.active_milestone_id == m2.id

    # -------------------------------------------------------------
    # Step 2: Underpromotion to Knight delivering Checkmate (f8=N#)
    # -------------------------------------------------------------
    m_f8n = chess.Move.from_uci("f7f8n")
    assert m_f8n in board.legal_moves

    pawn_before = tracker.get_piece_at(chess.F7)
    assert pawn_before is not None

    board_before = board.copy()
    board.push(m_f8n)
    tracker.apply_move(m_f8n, board_before, is_our_move=True)

    # Verify pawn is marked promoted, and new knight exists with correct lineage
    promoted_knight = tracker.get_piece_at(chess.F8)
    assert promoted_knight is not None
    assert promoted_knight.is_promoted is True
    assert promoted_knight.piece_type == chess.KNIGHT
    assert promoted_knight.promoted_from_id == pawn_before.piece_id

    # Verify surviving pawns is now 0
    surviving_now = tracker.get_surviving_pawns(chess.WHITE)
    assert len(surviving_now) == 0

    # Advance Milestone 2
    m2.status = MilestoneStatus.COMPLETED
    goal.advance_dag()
    assert m3.status == MilestoneStatus.ACTIVE

    # Verify Checkmate condition
    assert board.is_checkmate() is True
    assert board.result() == "1-0"

    # Advance Milestone 3
    m3.status = MilestoneStatus.COMPLETED
    goal.advance_dag()

    # Final Goal Verification
    assert goal.is_all_completed() is True
    assert goal.feasibility_status == FeasibilityStatus.COMPLETED
    report = feasibility_engine.evaluate(board, goal, tracker)
    assert report.status == FeasibilityStatus.COMPLETED


def test_tier1_king_sacrifice_strictly_forbidden():
    """Verify that attempting to sacrifice the King raises ValueError and NLP rejects it."""
    tracker = PieceTracker(chess.STARTING_FEN)
    king_piece = tracker.get_piece_at(chess.E1)
    assert king_piece is not None
    assert king_piece.is_king is True

    # Registering sacrifice intent with the King must be rejected immediately
    board = chess.Board()
    with pytest.raises(ValueError, match="The King is strictly excluded"):
        tracker.register_sacrifice_intent(
            piece_id=king_piece.piece_id,
            milestone_id="m1_sacrifice",
            move=chess.Move.from_uci("e1e2"),
            board=board,
        )

    # Natural Language instruction trying to sacrifice the king must be rejected
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Sacrifice the king and win the game", color="white")
    assert goal.is_ambiguous is True
    assert "King cannot be sacrificed" in goal.description


def test_tier1_blunder_and_equal_exchange_not_counted_as_sacrifice():
    """Verify that an untagged loss or an equal exchange is NOT a genuine sacrifice."""
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    tracker = PieceTracker(board.fen())
    tracker.set_our_color(chess.WHITE)

    # 1. Equal exchange: Nxe5 Nxe5 (Knight for Pawn or Knight for Knight)
    m1 = chess.Move.from_uci("f3e5")
    knight_p = tracker.get_piece_at(chess.F3)
    assert knight_p is not None

    # Tag intent with 3 points captured
    intent = tracker.register_sacrifice_intent(knight_p.piece_id, "m1", m1, board)
    intent.material_captured_on_offer = 3  # captured equal piece

    board_before = board.copy()
    board.push(m1)
    tracker.apply_move(m1, board_before, is_our_move=True, declared_intent=intent)

    # Black recaptures with knight: Nxe5
    m2 = chess.Move.from_uci("c6e5")
    board_before = board.copy()
    board.push(m2)
    tracker.apply_move(m2, board_before, is_our_move=False)

    sacs = tracker.get_confirmed_sacrifices(chess.WHITE)
    # Equal trade of 3 points for 3 points is NOT a genuine sacrifice
    assert len(sacs) == 0

    # 2. Untagged loss (blunder):
    # White blunders a piece without intent
    board2 = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 2")
    tracker2 = PieceTracker(board2.fen())
    tracker2.set_our_color(chess.WHITE)

    m_blunder = chess.Move.from_uci("d4d5")  # no intent registered
    board_before = board2.copy()
    board2.push(m_blunder)
    tracker2.apply_move(m_blunder, board_before, is_our_move=True, declared_intent=None)

    assert len(tracker2.get_confirmed_sacrifices(chess.WHITE)) == 0


def test_tier1_surviving_pawns_vs_original_8_pawns():
    """
    Verify distinction between 'every surviving pawn' and 'all 8 original pawns':
    - 'every surviving pawn': 1 pawn captured early -> remaining 7 can still succeed.
    - 'all 8 original pawns': 1 pawn captured -> PROVEN_IMPOSSIBLE.
    """
    board = chess.Board()
    tracker = PieceTracker(board.fen())
    tracker.set_our_color(chess.WHITE)
    feasibility_engine = FeasibilityEngine(our_color=chess.WHITE)

    # Goal A: Surviving pawns to knights
    goal_surviving = GoalInterpreter().parse_objective(
        "Promote every surviving pawn into a knight", color="white", force_deterministic=True
    )

    # Goal B: All 8 original pawns to knights
    goal_all_8 = GoalInterpreter().parse_objective(
        "Promote all 8 pawns into knights", color="white", force_deterministic=True
    )

    # White pawn on e2 is lost
    e2_pawn = tracker.get_piece_at(chess.E2)
    assert e2_pawn is not None
    e2_pawn.is_captured = True
    tracker.square_to_piece_id.pop(chess.E2, None)

    # Evaluate Goal A: surviving pawns remains FEASIBLE
    report_surviving = feasibility_engine.evaluate(board, goal_surviving, tracker)
    assert report_surviving.status == FeasibilityStatus.FEASIBLE

    # Evaluate Goal B: all 8 original pawns must be PROVEN_IMPOSSIBLE
    report_all_8 = feasibility_engine.evaluate(board, goal_all_8, tracker)
    assert report_all_8.status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "no_pawn_losses" in report_all_8.reason.lower() or "captured" in report_all_8.reason.lower()


def test_tier1_search_timeout_never_interpreted_as_impossible():
    """Verify that search timeout MUST NEVER transition status to PROVEN_IMPOSSIBLE."""
    board = chess.Board()
    tracker = PieceTracker(board.fen())
    goal = GoalInterpreter().parse_objective(
        "Sacrifice queen and win", color="white", force_deterministic=True
    )
    feasibility_engine = FeasibilityEngine(our_color=chess.WHITE)

    # When search budget expires, status remains UNRESOLVED, NEVER PROVEN_IMPOSSIBLE
    report = feasibility_engine.evaluate(board, goal, tracker, is_search_timeout=True)
    assert report.status != FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert report.status == FeasibilityStatus.UNRESOLVED


# =====================================================================
# TIER 2: LIVE ENGINE MATCH EXECUTION
# =====================================================================

@pytest.mark.asyncio
async def test_tier2_live_engine_match_execution():
    """
    Tier 2 Live Engine Match Test:
    Executes a live game between Machiavelli and calibrated Stockfish 1650 Elo,
    verifying clean UCI interaction, legal move generation, PGN annotations,
    and GameMetric output.
    """
    config = TournamentConfig(
        tiers=[1650],
        openings=get_openings()[:1],  # Test with Sicilian Defence
        games_per_opening=1,  # 1 live match
        movetime_ms=100,  # Fast time control for automated unit testing
        max_moves=10,  # 10 full moves
        output_dir="reports/test_benchmark",
        quick_mode=False,
    )

    runner = TournamentRunner(config)
    summary, games = await runner.run_tournament()

    assert len(games) == 1
    metric = games[0]
    assert metric.opponent_elo == 1650
    assert metric.opening_eco == "B90"
    assert metric.total_moves > 0
    assert metric.total_plies > 0
    assert metric.avg_move_time_ms > 0
    assert metric.pgn_text != ""
    assert "[Event " in metric.pgn_text
    assert "[MachiavelliObjective " in metric.pgn_text

    assert summary.total_games == 1
    assert os.path.exists("reports/test_benchmark/tournament_results.json")
    assert os.path.exists("reports/test_benchmark/tournament_games.csv")
    assert os.path.exists("reports/test_benchmark/tournament_games.pgn")
    assert os.path.exists("reports/test_benchmark/tournament_report.md")


# =====================================================================
# TIER 3: OPENINGS REPERTOIRE & BENCHMARK SUITE INTEGRATION
# =====================================================================

def test_openings_repertoire_completeness():
    """Verify all 15 openings exist, have valid FENs, valid ECOs, and legal SANs."""
    openings = get_openings()
    assert len(openings) == 15, "Repertoire must contain exactly 15 standard openings"

    ecos = {o.eco for o in openings}
    assert len(ecos) == 15, "Each opening must have a unique ECO code"

    for op in openings:
        assert op.eco != ""
        assert op.name != ""
        assert len(op.moves_san) >= 8, f"Opening {op.name} should have >= 8 plies"
        assert len(op.moves_uci) == len(op.moves_san)
        # Test creating board and checking FEN
        b = op.create_board()
        assert b.fen() == op.fen
        assert b.is_valid()


def test_benchmark_metrics_and_exporters(tmp_path):
    """Verify metric aggregation and JSON/CSV/PGN/Markdown exporters."""
    g1 = GameMetric(
        game_id="g1",
        tier_name="tier_1650",
        opponent_elo=1650,
        opening_eco="B90",
        opening_name="Sicilian Defence (Najdorf)",
        machiavelli_color="white",
        result="1-0",
        machiavelli_result="win",
        objective_completed=True,
        blunders=0,
        total_moves=25,
        total_plies=50,
        moves_to_completion=25,
        avg_move_time_ms=120.5,
        avg_eval_cp=45.0,
        sacrifices_count=1,
        promotions_count=1,
        termination_reason="checkmate",
        pgn_text="[Event \"Test\"]\n\n1. e4 c5 2. Nf3 d6 1-0\n",
    )

    summary = compute_tournament_summary([g1])
    assert summary.total_games == 1
    assert summary.wins == 1
    assert summary.win_rate == 1.0
    assert summary.objective_completed_count == 1
    assert summary.objective_completion_rate == 1.0
    assert summary.avg_blunders_per_game == 0.0

    json_f = str(tmp_path / "test.json")
    csv_f = str(tmp_path / "test.csv")
    pgn_f = str(tmp_path / "test.pgn")

    export_to_json(summary, [g1], json_f)
    export_to_csv([g1], csv_f)
    export_to_pgn([g1], pgn_f)

    assert os.path.exists(json_f)
    assert os.path.exists(csv_f)
    assert os.path.exists(pgn_f)

    md = generate_markdown_report(summary)
    assert "# Machiavelli Benchmark Tournament Report" in md
    assert "tier_1650" in md
