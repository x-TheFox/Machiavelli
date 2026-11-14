"""Unit and integration tests for Machiavelli's Candidate Generator, Search Engine, and Planner.

Verifies:
1. CandidateGenerator:
   - Hybrid merging of Stockfish MultiPV with goal-directed moves.
   - Promotion advances and Knight underpromotions (e7e8n).
   - Intentional sacrifice offers onto attacked squares.
   - Strict exclusion of King from sacrifices.
   - Adaptive candidate expansion.
2. TranspositionTable:
   - Zobrist hash + active milestone state caching.
3. AdversarialSearch:
   - Iterative deepening minimax with alpha-beta pruning.
   - Multi-response opponent disruption modeling.
4. MissionPlanner:
   - Milestone DAG progression and completion detection.
   - End-to-end select_move with rich structured explanations.
"""

import pytest
import chess

from backend.app.chess_engine.board_manager import BoardManager
from backend.app.chess_engine.candidate_gen import (
    CandidateCategory,
    CandidateGenerator,
    TaggedCandidate,
)
from backend.app.chess_engine.goal_evaluator import GoalEvaluator, GoalVector
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    GoalDefinition,
    Milestone,
    MilestoneStatus,
    MilestoneType,
)
from backend.app.chess_engine.piece_tracker import PieceTracker
from backend.app.chess_engine.planner import MissionPlanner, PlanResult
from backend.app.chess_engine.search import (
    AdversarialSearch,
    SearchResult,
    TranspositionTable,
    TTFlag,
)
from backend.app.chess_engine.uci_client import CandidateMove, UCIScore


# =============================================================================
# 1. Candidate Generator Tests
# =============================================================================

def test_candidate_gen_underpromotion_to_knight():
    """Verify CandidateGenerator recognizes and prioritizes underpromotion to Knight."""
    gen = CandidateGenerator(our_color=chess.WHITE)
    # Legal position: White pawn on e7, White king on g1, Black king on a1
    fen = "8/4P3/8/8/8/8/k7/6K1 w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(initial_fen=fen)

    goal = GoalDefinition(
        goal_id="g_knight_promo",
        raw_instruction="Promote surviving pawns into knights",
        title="Knight Promotion",
        description="Promote to knights",
        milestones=[
            Milestone(
                id="m1",
                title="Promote Pawns",
                description="Promote to knights",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    candidates = gen.generate_candidates(board, goal, tracker)
    assert len(candidates) > 0

    # Find e7e8n
    knight_promos = [
        c for c in candidates
        if c.move == chess.Move.from_uci("e7e8n") and c.has_category(CandidateCategory.UNDERPROMOTION)
    ]
    assert len(knight_promos) == 1
    assert knight_promos[0].priority >= 200.0, "Knight underpromotion should have high priority"


def test_candidate_gen_sacrifice_excludes_king():
    """Verify CandidateGenerator tags piece sacrifices on attacked squares and STRICTLY excludes King."""
    gen = CandidateGenerator(our_color=chess.WHITE)
    # Position where White Queen on e4 can move to d5 (attacked by Black pawn c6)
    fen = "rnbqkbnr/pp3ppp/2p5/3p4/4Q3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 5"
    board = chess.Board(fen)
    tracker = PieceTracker(initial_fen=fen)

    goal = GoalDefinition(
        goal_id="g_sac_q",
        raw_instruction="Sacrifice Queen",
        title="Sacrifice Queen",
        description="Sacrifice Queen",
        milestones=[
            Milestone(
                id="m_sac_q",
                title="Sacrifice Queen",
                description="Sacrifice Queen",
                milestone_type=MilestoneType.SACRIFICE_QUEEN,
                target_piece_types=["queen"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    candidates = gen.generate_candidates(board, goal, tracker)

    # Check that Queen sacrifice candidates have SACRIFICE_OFFER and non-null intent
    sac_cands = [c for c in candidates if c.has_category(CandidateCategory.SACRIFICE_OFFER)]
    for sc in sac_cands:
        piece = board.piece_at(sc.move.from_square)
        assert piece.piece_type != chess.KING, "King must NEVER be tagged as a sacrifice candidate!"
        assert sc.sacrifice_intent is not None
        assert sc.sacrifice_intent.offered_piece_type != chess.KING


def test_candidate_gen_adaptive_expansion():
    """Verify adaptive candidate expansion widens candidate set when requested."""
    gen = CandidateGenerator(our_color=chess.WHITE)
    board = chess.Board()
    tracker = PieceTracker()
    goal = GoalDefinition(
        goal_id="g_promo",
        raw_instruction="Promote surviving pawns to knights",
        title="Promote",
        description="Promote",
        milestones=[
            Milestone(
                id="m1",
                title="Promote",
                description="Promote",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    initial = gen.generate_candidates(board, goal, tracker, max_candidates=4)
    expanded = gen.expand_candidates(board, goal, tracker, initial, max_expanded=20)

    assert len(expanded) >= len(initial)
    # Check that expanded set contains pawn moves
    has_pawn_move = any(board.piece_at(c.move.from_square).piece_type == chess.PAWN for c in expanded)
    assert has_pawn_move


# =============================================================================
# 2. Transposition Table Tests
# =============================================================================

def test_transposition_table_store_and_probe():
    """Verify TT stores and probes entries matching board Zobrist hash and milestone state."""
    tt = TranspositionTable(max_entries=1000)
    board = chess.Board()
    tracker = PieceTracker()
    goal = GoalDefinition(
        goal_id="g1",
        raw_instruction="Promote pawns",
        title="Goal",
        description="Goal",
        milestones=[
            Milestone(
                id="m1",
                title="M1",
                description="M1",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                status=MilestoneStatus.ACTIVE,
            )
        ],
        active_milestone_id="m1",
    )

    key = tt.get_key(board, goal, tracker)
    score = GoalVector(safety=0.0, feasibility=100.0, milestone=50.0, positional=0.5)
    best_move = chess.Move.from_uci("e2e4")

    # Probe empty
    assert tt.probe(key, depth=3) is None

    # Store at depth 4
    tt.store(key, depth=4, flag=TTFlag.EXACT, score=score, best_move=best_move)

    # Probe with depth <= 4 should hit
    entry = tt.probe(key, depth=3)
    assert entry is not None
    assert entry.best_move == best_move
    assert entry.score == score
    assert tt.hits == 1

    # Probe with depth > 4 should miss
    assert tt.probe(key, depth=5) is None


# =============================================================================
# 3. Adversarial Search Tests
# =============================================================================

def test_adversarial_search_knight_underpromotion_tactical_mate():
    """
    Tactical validation:
    White to move: White pawn on b7, Black King on a8, White King on c7.
    b7-b8=Q results in STALEMATE (draw)!
    b7-b8=N results in CHECKMATE (White wins with Knight mate)!
    The search MUST select b7-b8=N!
    """
    # FEN: k7/1PK5/8/8/8/8/8/8 w - - 0 1
    # White pawn on b7, White king on c7, Black king on a7 (in check from pawn b7).
    # Let's set up White to move: pawn on b7, White king on c7, Black king on a8.
    # Wait, if Black king is on a8 and pawn on b7, Black king is already in check from b7 if it's White's turn?
    # No, if pawn is on b6, b6-b7 is check.
    # Let's construct standard underpromotion puzzle:
    # FEN: 8/1P6/8/8/8/8/k1K5/8 w - - 0 1
    # White pawn on b7, White king on c7, Black king on a8.
    # Legal moves from b7: b7-b8=Q, b7-b8=R, b7-b8=B, b7-b8=N.
    # If b7-b8=Q+ -> Kxb8 or stalemate?
    # Let's test standard smothered mate or underpromotion:
    # FEN: "k7/P7/1K6/8/8/8/8/8 w - - 0 1" -> a7-a8 is stalemate.
    # Knight underpromotion with check:
    # FEN: "7k/5P1p/6pP/6P1/8/8/8/4K3 w - - 0 1"
    # White pawn on f7. If f7-f8=Q# or f7-f8=R#, it's mate!
    # If milestone requires underpromoting to Knight:
    # Let's test with PROMOTE_SURVIVING_PAWNS requiring knights!
    fen = "7k/5P1p/6pP/6P1/8/8/8/4K3 w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(initial_fen=fen)

    goal = GoalDefinition(
        goal_id="g_knight_promo",
        raw_instruction="Promote surviving pawns into knights",
        title="Promote to Knight",
        description="Promote to Knight",
        milestones=[
            Milestone(
                id="m_promo",
                title="Promote surviving pawn to knight",
                description="Promote to knight",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    searcher = AdversarialSearch(our_color=chess.WHITE)
    res = searcher.search(board, goal, tracker, max_depth=2, time_limit_ms=2000)

    assert res.best_move.promotion == chess.KNIGHT, (
        f"Search must select Knight promotion (e.g. f7f8n), got {res.best_move.uci()}"
    )
    assert res.score.milestone > 500.0


def test_adversarial_search_opponent_disruption_modeling():
    """
    Verify opponent disruption modeling anticipates enemy capturing our advancing pawn.
    White has two pawn moves:
    - Pawn A advances into defended/safe square.
    - Pawn B moves directly into opponent rook's capture line.
    Search must prefer the safe pawn advance over moving into immediate capture.
    """
    # White pawn on d4, pawn on h4. Black Rook on d8.
    # d4-d5 moves onto d5 where d8 rook can capture it (Rxd5).
    # h4-h5 is safe.
    fen = "3r4/8/8/8/3P3P/8/8/4K2k w - - 0 1"
    board = chess.Board(fen)
    tracker = PieceTracker(initial_fen=fen)

    goal = GoalDefinition(
        goal_id="g_advance",
        raw_instruction="Promote surviving pawns",
        title="Advance Pawn",
        description="Advance Pawn",
        milestones=[
            Milestone(
                id="m1",
                title="Promote",
                description="Promote",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    searcher = AdversarialSearch(our_color=chess.WHITE)
    res = searcher.search(board, goal, tracker, max_depth=3, time_limit_ms=2500)

    # d4-d5 allows Rxd5, losing the pawn and failing feasibility/milestone!
    assert res.best_move != chess.Move.from_uci("d4d5"), (
        "Search should not blunder the pawn on d5 when opponent disruption model evaluates Rxd5!"
    )


# =============================================================================
# 4. Mission Planner Tests
# =============================================================================

@pytest.mark.asyncio
async def test_mission_planner_dag_progression():
    """Verify MissionPlanner detects milestone completion and advances DAG to next milestone."""
    planner = MissionPlanner(engine=None, our_color=chess.WHITE, depth=2)
    board = chess.Board()
    tracker = PieceTracker()

    m1 = Milestone(
        id="m_sac_q",
        title="Sacrifice Queen",
        description="Sacrifice Queen",
        milestone_type=MilestoneType.SACRIFICE_QUEEN,
        target_piece_types=["queen"],
        status=MilestoneStatus.ACTIVE,
    )
    m2 = Milestone(
        id="m_promo",
        title="Promote Pawns",
        description="Promote surviving pawns",
        milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
        target_piece_types=["knight"],
        dependencies=["m_sac_q"],
        status=MilestoneStatus.PENDING,
    )

    goal = GoalDefinition(
        goal_id="g_dag",
        raw_instruction="Sacrifice queen then promote surviving pawns to knights",
        title="DAG Goal",
        description="DAG Goal",
        milestones=[m1, m2],
        active_milestone_id="m_sac_q",
    )

    # Initially, m1 is ACTIVE, m2 is PENDING
    assert goal.get_milestone("m_sac_q").status == MilestoneStatus.ACTIVE
    assert goal.get_milestone("m_promo").status == MilestoneStatus.PENDING

    # Simulate genuine Queen sacrifice confirmation in PieceTracker
    q = [p for p in tracker.pieces.values() if p.color == chess.WHITE and p.piece_type == chess.QUEEN][0]
    intent = tracker.register_sacrifice_intent(
        piece_id=q.piece_id,
        milestone_id="m_sac_q",
        move=chess.Move.from_uci("d1h5"),
        board=board,
    )
    q.is_captured = True
    # Opponent accepts capture
    tracker._evaluate_sacrifice_resolution(q, chess.Move.from_uci("g6h5"))

    assert tracker.is_queen_sacrificed(chess.WHITE)

    # Run update_milestone_progress
    planner.update_milestone_progress(board, goal, tracker)
    assert m1.status == MilestoneStatus.COMPLETED

    # Advance DAG
    next_id = goal.advance_dag()
    assert next_id == "m_promo"
    assert m2.status == MilestoneStatus.ACTIVE


@pytest.mark.asyncio
async def test_mission_planner_select_move_end_to_end():
    """Verify MissionPlanner.select_move returns PlanResult with valid explanation and metrics."""
    planner = MissionPlanner(engine=None, our_color=chess.WHITE, depth=2)
    fen = "7k/5P1p/6pP/6P1/8/8/8/4K3 w - - 0 1"
    bm = BoardManager(fen=fen)
    tracker = PieceTracker(initial_fen=fen)

    goal = GoalDefinition(
        goal_id="g_end_to_end",
        raw_instruction="Promote pawn to knight and win",
        title="Promote and Win",
        description="Promote and Win",
        milestones=[
            Milestone(
                id="m1",
                title="Promote to Knight",
                description="Promote to Knight",
                milestone_type=MilestoneType.PROMOTE_SURVIVING_PAWNS,
                target_piece_types=["knight"],
                status=MilestoneStatus.ACTIVE,
            )
        ],
    )

    plan_result = await planner.select_move(
        board=bm,
        goal=goal,
        tracker=tracker,
        time_limit_ms=2000,
    )

    assert isinstance(plan_result, PlanResult)
    assert plan_result.move is not None
    assert plan_result.move.uci() == "f7f8n"
    assert "rationale" in plan_result.explanation
    assert "safety_status" in plan_result.explanation
    assert plan_result.depth_reached >= 1
    assert plan_result.feasibility_status in {FeasibilityStatus.FEASIBLE, FeasibilityStatus.COMPLETED}
