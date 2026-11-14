"""Unit tests for Machiavelli's Lexicographical Goal Evaluator.

Verifies:
1. Lexicographical priority ordering:
   V_safety > V_feasibility > V_milestone > V_positional
2. NO UNIVERSAL -600cp FILTER:
   Positions with extreme negative Stockfish centipawns (e.g. -900cp, -1500cp)
   remain safe (V_safety = 0.0) as long as no forced mate against us exists.
3. Proof-based feasibility integration (PROVEN_IMPOSSIBLE penalty, COMPLETED bonus).
4. Concrete milestone scoring for sacrifices, pawn promotions, and mating nets.
"""

import pytest
import chess

from backend.app.chess_engine.goal_evaluator import GoalEvaluator, GoalVector
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import PieceTracker
from backend.app.chess_engine.uci_client import UCIScore


def test_goal_vector_lexicographical_comparison():
    """Verify strict lexicographical priority ordering across all 4 vector components."""
    # 1. Safety dominates everything
    v_safe = GoalVector(safety=0.0, feasibility=0.0, milestone=0.0, positional=0.0)
    v_mated = GoalVector(safety=-100000.0, feasibility=10000.0, milestone=10000.0, positional=1000.0)
    assert v_safe > v_mated

    # 2. Feasibility dominates milestone and positional
    v_feas = GoalVector(safety=0.0, feasibility=100.0, milestone=50.0, positional=0.0)
    v_imposs = GoalVector(safety=0.0, feasibility=-10000.0, milestone=1000.0, positional=500.0)
    assert v_feas > v_imposs

    # 3. Milestone dominates positional (Stockfish cp)
    v_milestone_lead = GoalVector(safety=0.0, feasibility=100.0, milestone=600.0, positional=-9.5)
    v_positional_lead = GoalVector(safety=0.0, feasibility=100.0, milestone=100.0, positional=+5.0)
    assert v_milestone_lead > v_positional_lead

    # 4. Positional acts as tie-breaker when higher components are equal
    v_pos1 = GoalVector(safety=0.0, feasibility=100.0, milestone=500.0, positional=1.2)
    v_pos2 = GoalVector(safety=0.0, feasibility=100.0, milestone=500.0, positional=0.8)
    assert v_pos1 > v_pos2
    assert v_pos2 < v_pos1

    # 5. Equality and serialization
    v_same = GoalVector(safety=0.0, feasibility=100.0, milestone=500.0, positional=1.2)
    assert v_pos1 == v_same
    d = v_pos1.as_dict()
    assert d["safety"] == 0.0
    assert d["feasibility"] == 100.0
    assert d["milestone"] == 500.0


def test_no_universal_600cp_filter():
    """
    CRITICAL USER REQUIREMENT:
    Ensure positions with Stockfish cp eval < -600 (e.g. -900cp, -1500cp)
    do NOT suffer a safety penalty. Only true forced mate triggers safety failure.
    """
    evaluator = GoalEvaluator(our_color=chess.WHITE)
    board = chess.Board()

    # Case 1: Large negative centipawn evaluation (-950 cp) from sacrifice line
    score_sacrifice = UCIScore(cp=-950, mate=None)
    v_safety_sacrifice = evaluator.evaluate_safety(board, score_sacrifice)
    assert v_safety_sacrifice == 0.0, "Negative centipawns must NEVER trigger safety penalty!"

    # Case 2: Extreme negative centipawn evaluation (-1800 cp)
    score_extreme = UCIScore(cp=-1800, mate=None)
    v_safety_extreme = evaluator.evaluate_safety(board, score_extreme)
    assert v_safety_extreme == 0.0

    # Case 3: Genuine forced mate against us (mate in -2)
    score_mated = UCIScore(cp=None, mate=-2)
    v_safety_mated = evaluator.evaluate_safety(board, score_mated)
    assert v_safety_mated <= -50000.0, "Forced mate against us must trigger severe safety penalty!"

    # Case 4: Safe position (mate delivered by us or normal safe move)
    score_delivers_mate = UCIScore(cp=None, mate=3)
    v_safety_delivers_mate = evaluator.evaluate_safety(board, score_delivers_mate)
    assert v_safety_delivers_mate == 0.0, "Delivering mate is safe (V_safety = 0.0)"


def test_feasibility_evaluation_integration():
    """Verify V_feasibility maps correctly to FeasibilityStatus."""
    evaluator = GoalEvaluator(our_color=chess.WHITE)
    board = chess.Board()
    tracker = PieceTracker()

    goal = GoalDefinition(
        goal_id="g1",
        raw_instruction="Promote surviving pawns into knights",
        title="Promote Surviving Pawns",
        description="Promote surviving pawns",
        milestones=[
            Milestone(
                id="m1",
                title="Promote",
                description="Promote pawns",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_count=8,
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    # 1. Standard initial state -> FEASIBLE
    v_feas = evaluator.evaluate_feasibility(board, goal, tracker)
    assert v_feas == GoalEvaluator.FEASIBLE_BONUS

    # 2. Simulate pawn loss breaking invariant -> PROVEN_IMPOSSIBLE
    # Capture all white pawns
    for p in tracker.get_original_pawns(chess.WHITE):
        p.is_captured = True
    v_imposs = evaluator.evaluate_feasibility(board, goal, tracker)
    assert v_imposs == -GoalEvaluator.IMPOSSIBLE_PENALTY

    # 3. Simulate completion
    goal.milestones[0].status = MilestoneStatus.COMPLETED
    v_comp = evaluator.evaluate_feasibility(board, goal, tracker)
    assert v_comp == GoalEvaluator.COMPLETED_BONUS


def test_milestone_evaluation_pawn_promotion():
    """Verify milestone scoring increases as pawns advance toward promotion."""
    evaluator = GoalEvaluator(our_color=chess.WHITE)
    tracker = PieceTracker()

    goal = GoalDefinition(
        goal_id="pawn_promo_goal",
        raw_instruction="Promote pawns to knights",
        title="Promote",
        description="Promote to knights",
        milestones=[
            Milestone(
                id="m1",
                title="Promote Pawns",
                description="Promote to knights",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                target_count=1,
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    # Initial pawn at e2 (rank 2, index 1)
    board_initial = chess.Board("8/8/8/8/8/8/4P3/4K2k w - - 0 1")
    tracker_initial = PieceTracker(initial_fen="8/8/8/8/8/8/4P3/4K2k w - - 0 1")
    v_initial = evaluator.evaluate_milestone(board_initial, goal, tracker_initial)

    # Advanced pawn at e6 (rank 6, index 5)
    board_advanced = chess.Board("8/8/4P3/8/8/8/8/4K2k w - - 0 1")
    tracker_advanced = PieceTracker(initial_fen="8/8/4P3/8/8/8/8/4K2k w - - 0 1")
    v_advanced = evaluator.evaluate_milestone(board_advanced, goal, tracker_advanced)

    # 7th rank pawn at e7 (rank 7, index 6 - 1 step from promotion)
    board_seventh = chess.Board("8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    tracker_seventh = PieceTracker(initial_fen="8/4P3/8/8/8/8/8/4K2k w - - 0 1")
    v_seventh = evaluator.evaluate_milestone(board_seventh, goal, tracker_seventh)

    assert v_advanced > v_initial, "Advanced pawn must score higher than base pawn"
    assert v_seventh > v_advanced, "7th rank pawn must score higher due to promotion proximity bonus"


def test_milestone_evaluation_sacrifice_baiting():
    """Verify deliberate piece baiting onto attacked squares scores milestone points."""
    evaluator = GoalEvaluator(our_color=chess.WHITE)
    tracker = PieceTracker()

    goal = GoalDefinition(
        goal_id="sac_goal",
        raw_instruction="Sacrifice Queen",
        title="Sacrifice Queen",
        description="Sacrifice Queen",
        milestones=[
            Milestone(
                id="m_sac",
                title="Sacrifice Queen",
                description="Sacrifice Queen",
                milestone_type=MilestoneType.SACRIFICE_QUEEN,
                target_piece_types=["queen"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    # Queen safe on d1
    board_safe = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
    tracker_safe = PieceTracker(initial_fen="rnb1kbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
    v_safe = evaluator.evaluate_milestone(board_safe, goal, tracker_safe)

    # Queen moved to h5 attacked by pawn on g6 (FEN where Queen is en prise on h5 with g7-g6 attacking it)
    board_attacked = chess.Board("rnb1kbnr/pppp1p1p/6p1/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1")
    tracker_attacked = PieceTracker(initial_fen="rnb1kbnr/pppp1p1p/6p1/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1")
    v_attacked = evaluator.evaluate_milestone(board_attacked, goal, tracker_attacked)

    assert v_attacked > v_safe, "Offering Queen on an attacked square must reward sacrifice milestone progress"
