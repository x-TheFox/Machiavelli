import json
from unittest.mock import MagicMock, patch
import openai
import pytest

from backend.app.chess_engine.goal_interpreter import GoalInterpreter
from backend.app.chess_engine.goal_schema import (
    FeasibilityStatus,
    MilestoneStatus,
    MilestoneType,
)


def test_section_11_benchmark_goal_dag():
    interpreter = GoalInterpreter()
    instruction = (
        "Sacrifice all original pieces, promote every surviving pawn into a knight, "
        "and checkmate using the promoted knights"
    )
    goal = interpreter.parse_objective(instruction, color="white")

    assert not goal.is_ambiguous
    assert len(goal.milestones) == 3
    assert goal.validate_dag() is True

    m1, m2, m3 = goal.milestones
    assert m1.milestone_type == MilestoneType.SACRIFICE_ALL_ORIGINAL_PIECES
    assert m1.target_count == 7
    assert m1.status == MilestoneStatus.ACTIVE
    assert m1.dependencies == []

    assert m2.milestone_type == MilestoneType.PROMOTE_SURVIVING_PAWNS
    assert "knight" in m2.target_piece_types
    assert m2.status == MilestoneStatus.PENDING
    assert m2.dependencies == [m1.id]

    assert m3.milestone_type == MilestoneType.CHECKMATE_WITH_PIECE
    assert m3.conditions.get("require_promoted_lineage") is True
    assert m3.status == MilestoneStatus.PENDING
    assert m3.dependencies == [m2.id]

    # Test topological order
    order = goal.get_topological_order()
    assert order == [m1.id, m2.id, m3.id]

    # Test advancing DAG
    m1.status = MilestoneStatus.COMPLETED
    next_active = goal.advance_dag()
    assert next_active == m2.id
    assert m2.status == MilestoneStatus.ACTIVE

    m2.status = MilestoneStatus.COMPLETED
    next_active = goal.advance_dag()
    assert next_active == m3.id
    assert m3.status == MilestoneStatus.ACTIVE

    m3.status = MilestoneStatus.COMPLETED
    next_active = goal.advance_dag()
    assert next_active is None
    assert goal.is_all_completed() is True
    assert goal.feasibility_status == FeasibilityStatus.COMPLETED


def test_promote_surviving_pawns():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Promote all surviving pawns to knights")
    assert not goal.is_ambiguous
    assert len(goal.milestones) == 2
    assert goal.milestones[0].milestone_type == MilestoneType.PROMOTE_SURVIVING_PAWNS
    assert goal.milestones[0].conditions.get("all_surviving") is True


def test_promote_all_8_pawns_invariant():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Promote all 8 pawns to queens")
    assert not goal.is_ambiguous
    assert len(goal.invariants) == 1
    assert goal.invariants[0].no_pawn_losses is True
    assert goal.milestones[0].milestone_type == MilestoneType.PROMOTE_ALL_8_PAWNS
    assert goal.milestones[0].target_count == 8


def test_queen_sacrifice_goal():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Sacrifice the queen and win")
    assert not goal.is_ambiguous
    assert goal.milestones[0].milestone_type == MilestoneType.SACRIFICE_QUEEN
    assert goal.milestones[0].target_count == 1


def test_piece_checkmates():
    interpreter = GoalInterpreter()
    rook_goal = interpreter.parse_objective("Checkmate with a rook")
    assert not rook_goal.is_ambiguous
    assert rook_goal.milestones[0].milestone_type == MilestoneType.CHECKMATE_WITH_PIECE
    assert rook_goal.milestones[0].target_piece_types == ["rook"]

    knight_goal = interpreter.parse_objective("Checkmate with a knight")
    assert not knight_goal.is_ambiguous
    assert knight_goal.milestones[0].milestone_type == MilestoneType.CHECKMATE_WITH_PIECE
    assert knight_goal.milestones[0].target_piece_types == ["knight"]


def test_zero_captures_invariant():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Win the game without capturing any pieces")
    assert not goal.is_ambiguous
    assert len(goal.invariants) == 1
    assert goal.invariants[0].max_our_captures == 0


def test_win_under_move_limit():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Win the game in under 35 moves")
    assert not goal.is_ambiguous
    assert len(goal.invariants) == 1
    assert goal.invariants[0].max_moves == 35


def test_king_sacrifice_strictly_rejected():
    interpreter = GoalInterpreter()
    goal = interpreter.parse_objective("Sacrifice the king to confuse opponent")
    assert goal.is_ambiguous is True
    assert goal.feasibility_status == FeasibilityStatus.PROVEN_IMPOSSIBLE
    assert "King cannot be sacrificed" in goal.status_reason


def test_unsupported_instruction_clean_rejection():
    interpreter = GoalInterpreter(api_key="")  # No LLM key
    goal = interpreter.parse_objective("Play some weird moves and vibe", force_deterministic=True)
    assert goal.is_ambiguous is True
    assert goal.clarification_prompt is not None
    assert "could not be compiled" in goal.clarification_prompt


def test_llm_fallback_parsing():
    mock_llm_json = {
        "goal_id": "custom_goal_1",
        "title": "Castling Defense",
        "description": "Castle kingside within 10 moves",
        "milestones": [
            {
                "id": "m1_castle",
                "title": "Castle Kingside",
                "description": "Perform kingside castle",
                "milestone_type": "CUSTOM",
                "target_piece_types": ["king", "rook"],
                "target_piece_ids": [],
                "target_count": 1,
                "dependencies": [],
                "conditions": {},
            }
        ],
        "invariants": [],
        "is_ambiguous": False,
        "clarification_prompt": None,
    }

    interpreter = GoalInterpreter(api_key="mock_key")

    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        import json
        mock_choice.message.content = json.dumps(mock_llm_json)
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        goal = interpreter.parse_objective("Castle kingside within 10 moves")
        assert not goal.is_ambiguous
        assert goal.goal_id == "custom_goal_1"
        assert len(goal.milestones) == 1
        assert goal.milestones[0].milestone_type == MilestoneType.CUSTOM


def test_llm_model_chaining_failover():
    mock_llm_json = {
        "goal_id": "failover_goal",
        "title": "Failover Succeeded",
        "description": "Passed on fallback model",
        "milestones": [
            {
                "id": "m1_fallback",
                "title": "Fallback Milestone",
                "description": "Completed via secondary model",
                "milestone_type": "CUSTOM",
                "target_piece_types": [],
                "target_piece_ids": [],
                "target_count": 1,
                "dependencies": [],
                "conditions": {},
            }
        ],
        "invariants": [],
        "is_ambiguous": False,
        "clarification_prompt": None,
    }

    interpreter = GoalInterpreter(api_key="mock_key")

    with patch("openai.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client

        mock_completion = MagicMock()
        mock_choice = MagicMock()
        import json
        mock_choice.message.content = json.dumps(mock_llm_json)
        mock_completion.choices = [mock_choice]

        # First model call raises RateLimitError / 429, second call succeeds
        mock_client.chat.completions.create.side_effect = [
            openai.RateLimitError(
                message="Rate limit exceeded",
                response=MagicMock(status_code=429, headers={}),
                body={"error": "rate_limit"},
            ),
            mock_completion,
        ]

        goal = interpreter.parse_objective("Perform a tricky knight fork")
        assert not goal.is_ambiguous
        assert goal.goal_id == "failover_goal"
        assert mock_client.chat.completions.create.call_count == 2
