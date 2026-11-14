"""REST API Routes for Project Machiavelli.

Endpoints:
- /api/health
- /api/openings
- /api/games (GET, POST)
- /api/games/{session_id} (GET, DELETE)
- /api/games/{session_id}/state (GET)
- /api/games/{session_id}/move (POST)
- /api/games/{session_id}/step (POST)
- /api/games/{session_id}/fallback (POST)
- /api/games/{session_id}/pause (POST)
- /api/games/{session_id}/resume (POST)
- /api/benchmark/runs (GET, POST)
- /api/benchmark/runs/{run_id} (GET)
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

import chess
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.core.models import BenchmarkRun, GameRecord, MilestoneRecord, MoveRecord
from backend.app.chess_engine.game_session import GameSession, session_manager
from backend.app.benchmark.openings import get_openings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Machiavelli API"])


# --------------------------------------------------------------------------
# Request & Response Schemas
# --------------------------------------------------------------------------

class CreateGameRequest(BaseModel):
    goal_text: str = Field(default="", description="Natural language chess goal")
    mode: str = Field(default="interactive", description="'interactive' or 'benchmark'")
    machiavelli_color: str = Field(default="white", description="'white' or 'black'")
    opponent_type: str = Field(default="stockfish", description="'stockfish' or 'human'")
    opponent_elo: Optional[int] = Field(default=1950, description="Calibrated Elo rating for opponent")
    start_fen: Optional[str] = Field(default=None, description="Starting FEN position if non-standard")
    session_id: Optional[str] = Field(default=None, description="Optional custom session UUID")


class PlayerMoveRequest(BaseModel):
    move: str = Field(..., description="Move in UCI (e.g. 'e2e4') or SAN (e.g. 'e4')")


class FallbackChoiceRequest(BaseModel):
    choice: str = Field(..., description="'relax_constraint', 'conventional_win', or 'resign'")
    params: Optional[Dict[str, Any]] = Field(default=None, description="Optional relaxation parameters")


class BenchmarkRunCreateRequest(BaseModel):
    id: Optional[str] = None
    tier_name: str
    engine_name: str = "Stockfish 19"
    opponent_elo: int
    total_games: int
    games_won: int
    games_drawn: int
    games_lost: int
    objective_completed_count: int
    objective_failed_count: int
    avg_moves: Optional[float] = None
    avg_nodes: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    results: Optional[Dict[str, Any]] = None


# --------------------------------------------------------------------------
# System & Meta Endpoints
# --------------------------------------------------------------------------

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Service health check endpoint."""
    return {
        "status": "ok",
        "service": "machiavelli",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/openings")
async def list_openings() -> List[Dict[str, Any]]:
    """List 15 standard diverse ECO opening repertoire."""
    openings = get_openings()
    return [op.to_dict() for op in openings]


# --------------------------------------------------------------------------
# Game Session Endpoints
# --------------------------------------------------------------------------

@router.post("/games", status_code=status.HTTP_201_CREATED)
async def create_game(
    req: CreateGameRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create and initialize a new Machiavelli game session."""
    color = chess.WHITE if req.machiavelli_color.lower() == "white" else chess.BLACK

    session = await session_manager.create_session(
        goal_text=req.goal_text,
        mode=req.mode,
        machiavelli_color=color,
        opponent_type=req.opponent_type,
        opponent_elo=req.opponent_elo,
        start_fen=req.start_fen,
        session_id=req.session_id,
    )

    # Persist initial record in SQLite
    game_rec = GameRecord(
        id=session.session_id,
        goal_text=session.raw_goal_text,
        mode=session.mode,
        status="active",
        fen=session.board.fen,
        start_fen=session.start_fen,
        machiavelli_color="white" if session.machiavelli_color == chess.WHITE else "black",
        opponent_type=session.opponent_type,
        opponent_elo=session.opponent_elo,
        moves_count=0,
    )
    db.add(game_rec)
    await db.commit()

    return {
        "status": "created",
        "session_id": session.session_id,
        "state": session.get_state_snapshot(),
    }


@router.get("/games")
async def list_games(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List historical and active games with pagination."""
    query = select(GameRecord).order_by(desc(GameRecord.created_at)).limit(limit).offset(offset)
    if mode:
        query = query.where(GameRecord.mode == mode)
    if status_filter:
        query = query.where(GameRecord.status == status_filter)

    result = await db.execute(query)
    records = result.scalars().all()

    active_sessions = await session_manager.list_active_sessions()
    active_ids = {s["session_id"] for s in active_sessions}

    games_data = []
    for r in records:
        d = r.to_dict()
        d["is_active"] = r.id in active_ids
        games_data.append(d)

    return {
        "total": len(games_data),
        "limit": limit,
        "offset": offset,
        "games": games_data,
        "active_sessions_count": len(active_sessions),
    }


@router.get("/games/{session_id}")
async def get_game(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve full details of a specific game session."""
    active_session = await session_manager.get_session(session_id)
    if active_session:
        return {
            "source": "memory",
            "is_active": True,
            "state": active_session.get_state_snapshot(),
        }

    # Query from database if not active in memory
    result = await db.execute(select(GameRecord).where(GameRecord.id == session_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game session '{session_id}' not found",
        )

    return {
        "source": "database",
        "is_active": False,
        "record": record.to_dict(),
    }


@router.get("/games/{session_id}/state")
async def get_game_state(session_id: str) -> Dict[str, Any]:
    """Get real-time authoritative snapshot of active session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active game session '{session_id}' not found",
        )
    return session.get_state_snapshot()


@router.post("/games/{session_id}/move")
async def make_move(
    session_id: str,
    req: PlayerMoveRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Submit a player move to an active game session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active game session '{session_id}' not found",
        )

    fen_before = session.board.fen
    result = await session.execute_player_move(req.move)
    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("message", "Move rejected"),
        )

    # Persist move record
    try:
        last_move = session.board.board.peek()
        move_rec = MoveRecord(
            game_id=session.session_id,
            move_number=session.board.fullmove_number,
            ply=session.board.ply,
            uci=last_move.uci(),
            san=session.board.move_to_san(last_move),
            player="player",
            fen_before=fen_before,
            fen_after=session.board.fen,
        )
        db.add(move_rec)
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not persist move to DB: {e}")

    return result


@router.post("/games/{session_id}/step")
async def step_engine(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger one automated move step for the current turn."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active game session '{session_id}' not found",
        )

    fen_before = session.board.fen
    result = await session.step_turn()

    if result.get("status") == "ok":
        try:
            last_move = session.board.board.peek()
            is_sac = False
            sac_piece = None
            sac_target = None
            if session.last_explanation and session.last_explanation.get("is_sacrifice"):
                is_sac = True

            move_rec = MoveRecord(
                game_id=session.session_id,
                move_number=session.board.fullmove_number,
                ply=session.board.ply,
                uci=result.get("move", ""),
                san=result.get("san", ""),
                player=result.get("player", "engine"),
                fen_before=fen_before,
                fen_after=session.board.fen,
                stockfish_eval_cp=(
                    session.last_analysis.top_candidate.score.cp
                    if (session.last_analysis and session.last_analysis.top_candidate)
                    else None
                ),
                stockfish_eval_mate=(
                    session.last_analysis.top_candidate.score.mate
                    if (session.last_analysis and session.last_analysis.top_candidate)
                    else None
                ),
                is_sacrifice=is_sac,
                sacrifice_piece=sac_piece,
                sacrifice_target_milestone=sac_target,
                decision_explanation=json.dumps(session.last_explanation) if session.last_explanation else None,
                candidate_moves_json=json.dumps(session.last_candidate_moves) if session.last_candidate_moves else None,
            )
            db.add(move_rec)
            await db.commit()
        except Exception as e:
            logger.warning(f"Could not persist engine move to DB: {e}")

    return result


@router.post("/games/{session_id}/fallback")
async def resolve_fallback(
    session_id: str,
    req: FallbackChoiceRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Submit user selection for impossibility fallback prompt."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active game session '{session_id}' not found",
        )

    res = await session.handle_fallback_choice(req.choice, req.params)
    if res.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("message", "Invalid fallback choice"),
        )

    # Update DB record with updated status
    try:
        db_game = await db.get(GameRecord, session.session_id)
        if db_game:
            db_game.status = session.status
            db_game.objective_failed = session.objective_failed
            db_game.impossibility_evidence = session.impossibility_evidence
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to update game record after fallback: {e}")

    return res


@router.post("/games/{session_id}/pause")
async def pause_game(session_id: str) -> Dict[str, Any]:
    """Pause automated engine moves in active session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_paused = True
    await session.broadcast_event("GAME_PAUSED", {"session_id": session_id})
    return {"status": "ok", "is_paused": True}


@router.post("/games/{session_id}/resume")
async def resume_game(session_id: str) -> Dict[str, Any]:
    """Resume automated engine moves in paused session."""
    session = await session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_paused = False
    await session.broadcast_event("GAME_RESUMED", {"session_id": session_id})
    return {"status": "ok", "is_paused": False}


@router.delete("/games/{session_id}")
async def close_game(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Close active game session and save final state."""
    session = await session_manager.get_session(session_id)
    if session:
        # Sync final state to DB
        try:
            db_game = await db.get(GameRecord, session_id)
            if db_game:
                db_game.fen = session.board.fen
                db_game.status = session.status
                db_game.result = session.result
                db_game.termination_reason = session.termination_reason
                db_game.objective_completed = session.objective_completed
                db_game.objective_failed = session.objective_failed
                db_game.impossibility_evidence = session.impossibility_evidence
                db_game.pgn = session._build_pgn()
                await db.commit()
        except Exception as e:
            logger.warning(f"Error saving game state on delete: {e}")

        closed = await session_manager.close_session(session_id)
        return {"status": "closed", "session_id": session_id, "success": closed}

    raise HTTPException(status_code=404, detail="Active session not found")


# --------------------------------------------------------------------------
# Benchmark Runs Endpoints
# --------------------------------------------------------------------------

@router.get("/benchmark/runs")
async def list_benchmark_runs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    tier: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List historical benchmark runs with summary metrics."""
    query = select(BenchmarkRun).order_by(desc(BenchmarkRun.created_at)).limit(limit).offset(offset)
    if tier:
        query = query.where(BenchmarkRun.tier_name == tier)

    result = await db.execute(query)
    records = result.scalars().all()

    return {
        "total": len(records),
        "limit": limit,
        "offset": offset,
        "runs": [r.to_dict() for r in records],
    }


@router.get("/benchmark/runs/{run_id}")
async def get_benchmark_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve detailed metrics for a single benchmark run."""
    run = await db.get(BenchmarkRun, run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Benchmark run '{run_id}' not found",
        )
    return run.to_dict()


@router.post("/benchmark/runs", status_code=status.HTTP_201_CREATED)
async def create_benchmark_run(
    req: BenchmarkRunCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Record or store completed tournament benchmark run."""
    run_id = req.id or str(uuid.uuid4())
    run = BenchmarkRun(
        id=run_id,
        tier_name=req.tier_name,
        engine_name=req.engine_name,
        opponent_elo=req.opponent_elo,
        total_games=req.total_games,
        games_won=req.games_won,
        games_drawn=req.games_drawn,
        games_lost=req.games_lost,
        objective_completed_count=req.objective_completed_count,
        objective_failed_count=req.objective_failed_count,
        avg_moves=req.avg_moves,
        avg_nodes=req.avg_nodes,
        config_json=json.dumps(req.config) if req.config else None,
        results_json=json.dumps(req.results) if req.results else None,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return {"status": "created", "run": run.to_dict()}
