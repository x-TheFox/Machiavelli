from backend.app.chess_engine.board_manager import BoardManager, IllegalMoveError
from backend.app.chess_engine.uci_client import (
    StockfishUCIClient,
    AnalysisResult,
    CandidateMove,
    UCIScore,
    UCIError,
    UCITimeoutError,
    UCICrashError,
)
from backend.app.chess_engine.piece_tracker import (
    PieceTracker,
    TrackedPiece,
    SacrificeIntent,
    SacrificeEvent,
)
from backend.app.chess_engine.goal_schema import (
    GoalDefinition,
    Milestone,
    MilestoneType,
    MilestoneStatus,
    FeasibilityStatus,
    FeasibilityReport,
    Invariant,
)
from backend.app.chess_engine.feasibility import FeasibilityEngine
from backend.app.chess_engine.goal_evaluator import GoalEvaluator, GoalVector
from backend.app.chess_engine.candidate_gen import (
    CandidateGenerator,
    TaggedCandidate,
    CandidateCategory,
)
from backend.app.chess_engine.search import (
    AdversarialSearch,
    SearchResult,
    TranspositionTable,
)
from backend.app.chess_engine.planner import MissionPlanner, PlanResult
from backend.app.chess_engine.game_session import GameSession, SessionManager, session_manager

__all__ = [
    "BoardManager",
    "IllegalMoveError",
    "StockfishUCIClient",
    "AnalysisResult",
    "CandidateMove",
    "UCIScore",
    "UCIError",
    "UCITimeoutError",
    "UCICrashError",
    "PieceTracker",
    "TrackedPiece",
    "SacrificeIntent",
    "SacrificeEvent",
    "GoalDefinition",
    "Milestone",
    "MilestoneType",
    "MilestoneStatus",
    "FeasibilityStatus",
    "FeasibilityReport",
    "Invariant",
    "FeasibilityEngine",
    "GoalEvaluator",
    "GoalVector",
    "CandidateGenerator",
    "TaggedCandidate",
    "CandidateCategory",
    "AdversarialSearch",
    "SearchResult",
    "TranspositionTable",
    "MissionPlanner",
    "PlanResult",
    "GameSession",
    "SessionManager",
    "session_manager",
]
