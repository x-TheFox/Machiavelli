"""Tests for Machiavelli GameSession, Database models, REST API, and WebSocket streaming."""

import asyncio
from datetime import datetime, timezone
import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import chess

from backend.app.main import app
from backend.app.core.database import init_db, async_session_maker, engine
from backend.app.core.models import Base, GameRecord, MoveRecord, BenchmarkRun
from backend.app.chess_engine.game_session import GameSession, SessionManager, compute_evidence_hash
from backend.app.chess_engine.goal_schema import FeasibilityStatus, FeasibilityReport
from sqlalchemy import select
from sqlalchemy.orm import selectinload


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Ensure database is freshly initialized before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_database_crud():
    """Verify database models persist and retrieve data properly."""
    async with async_session_maker() as session:
        game = GameRecord(
            id="test_game_123",
            goal_text="Sacrifice queen and win",
            mode="interactive",
            status="active",
            fen=chess.STARTING_FEN,
            start_fen=chess.STARTING_FEN,
            machiavelli_color="white",
            opponent_type="stockfish",
            opponent_elo=1950,
            moves_count=0,
        )
        session.add(game)
        await session.commit()

        # Add a move record
        move = MoveRecord(
            game_id="test_game_123",
            move_number=1,
            ply=1,
            uci="e2e4",
            san="e4",
            player="white",
            fen_before=chess.STARTING_FEN,
            fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            stockfish_eval_cp=35,
        )
        session.add(move)
        await session.commit()

        # Add benchmark run
        run = BenchmarkRun(
            id="bench_run_001",
            tier_name="tier_1950",
            opponent_elo=1950,
            total_games=10,
            games_won=6,
            games_drawn=2,
            games_lost=2,
            objective_completed_count=5,
            objective_failed_count=5,
        )
        session.add(run)
        await session.commit()

        # Verify retrieval with eager-loaded moves
        res = await session.execute(
            select(GameRecord).options(selectinload(GameRecord.moves)).where(GameRecord.id == "test_game_123")
        )
        fetched_game = res.scalar_one_or_none()
        assert fetched_game is not None
        assert fetched_game.goal_text == "Sacrifice queen and win"
        assert len(fetched_game.moves) == 1
        assert fetched_game.moves[0].uci == "e2e4"

        fetched_run = await session.get(BenchmarkRun, "bench_run_001")
        assert fetched_run is not None
        assert fetched_run.total_games == 10
        assert fetched_run.games_won == 6


@pytest.mark.asyncio
async def test_game_session_initialization_and_snapshot():
    """Verify GameSession initialization, state snapshot, and sequence increments."""
    session = GameSession(
        session_id="session_snap_test",
        goal_text="Promote surviving pawns into knights",
        mode="interactive",
        machiavelli_color=chess.WHITE,
    )
    # Don't need real engine start for state snapshot unit checks
    snap = session.get_state_snapshot()
    assert snap["session_id"] == "session_snap_test"
    assert snap["mode"] == "interactive"
    assert snap["machiavelli_color"] == "white"
    assert snap["turn"] == "white"
    assert snap["ply"] == 0
    assert snap["current_seq"] == 0
    assert "goal" in snap
    assert snap["goal"]["title"] != ""
    assert "piece_metrics" in snap
    assert snap["piece_metrics"]["surviving_pawns"] == 8


@pytest.mark.asyncio
async def test_dual_mode_impossibility_interactive():
    """Test interactive mode impossibility handler: FALLBACK_PROMPT emission and user choice."""
    session = GameSession(
        session_id="session_interactive_imp",
        goal_text="Sacrifice queen and win",
        mode="interactive",
    )

    events_received = []
    session.add_listener(lambda ev: events_received.append(ev))

    # Simulate impossibility report
    report = FeasibilityReport(
        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
        reason="Our queen was captured without sacrifice intent",
        broken_invariant_id="queen_sacrifice_invariant",
        evidence={"ply": 15, "captured": "q"},
    )
    await session._handle_impossibility(report)

    assert session.pending_fallback is True
    assert session.is_paused is True
    assert session.fallback_prompt_data is not None

    prompt_events = [ev for ev in events_received if ev["type"] == "FALLBACK_PROMPT"]
    assert len(prompt_events) == 1
    assert len(prompt_events[0]["payload"]["choices"]) == 3

    # User selects "conventional_win"
    choice_res = await session.handle_fallback_choice("conventional_win")
    assert choice_res["status"] == "ok"
    assert session.pending_fallback is False
    assert session.fallback_to_conventional is True
    assert session.objective_failed is True


@pytest.mark.asyncio
async def test_dual_mode_impossibility_benchmark():
    """Test benchmark mode impossibility handler: cryptographic evidence and auto Stockfish fallback."""
    session = GameSession(
        session_id="session_benchmark_imp",
        goal_text="Promote all 8 pawns into knights",
        mode="benchmark",
    )

    events_received = []
    session.add_listener(lambda ev: events_received.append(ev))

    report = FeasibilityReport(
        status=FeasibilityStatus.PROVEN_IMPOSSIBLE,
        reason="A pawn was captured, violating all-8-pawns invariant",
        broken_invariant_id="no_pawn_losses",
        evidence={"lost_pawn_id": "white_pawn_e2"},
    )
    await session._handle_impossibility(report)

    # In benchmark mode, must not pause for user prompt
    assert session.pending_fallback is False
    assert session.objective_failed is True
    assert session.fallback_to_conventional is True
    assert session.impossibility_evidence is not None

    evidence = json.loads(session.impossibility_evidence)
    assert "sha256_hash" in evidence
    assert len(evidence["sha256_hash"]) == 64

    notices = [ev for ev in events_received if ev["type"] == "FALLBACK_NOTICE"]
    assert len(notices) == 1
    assert notices[0]["payload"]["action"] == "conventional_fallback"


@pytest.mark.asyncio
async def test_sequence_reconnection():
    """Verify sequence monotonic increment and replay of missed events."""
    session = GameSession(
        session_id="session_reconnect_test",
        mode="interactive",
    )

    # Broadcast several events
    await session.broadcast_event("EVENT_A", {"data": 1})
    await session.broadcast_event("EVENT_B", {"data": 2})
    await session.broadcast_event("EVENT_C", {"data": 3})

    assert session.seq == 3
    assert len(session.event_history) == 3

    # Client reconnects having only seen seq 1
    missed = session.get_events_since(last_seq=1)
    assert len(missed) == 2
    assert missed[0]["seq"] == 2
    assert missed[0]["type"] == "EVENT_B"
    assert missed[1]["seq"] == 3
    assert missed[1]["type"] == "EVENT_C"


@pytest.mark.asyncio
async def test_rest_api_endpoints():
    """Verify REST endpoints via AsyncClient."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health
        res = await client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # 2. Openings
        res = await client.get("/api/openings")
        assert res.status_code == 200
        openings = res.json()
        assert len(openings) >= 15
        assert any(op["eco"] == "B90" for op in openings)

        # 3. Create Game
        res = await client.post(
            "/api/games",
            json={
                "goal_text": "Checkmate with rooks",
                "mode": "interactive",
                "machiavelli_color": "white",
                "opponent_elo": 1950,
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert "session_id" in data
        session_id = data["session_id"]

        # 4. Get Game
        res = await client.get(f"/api/games/{session_id}")
        assert res.status_code == 200
        assert res.json()["is_active"] is True

        # 5. List Games
        res = await client.get("/api/games")
        assert res.status_code == 200
        assert res.json()["total"] >= 1

        # 6. Benchmark Runs
        res = await client.post(
            "/api/benchmark/runs",
            json={
                "tier_name": "tier_1650",
                "opponent_elo": 1650,
                "total_games": 20,
                "games_won": 14,
                "games_drawn": 4,
                "games_lost": 2,
                "objective_completed_count": 12,
                "objective_failed_count": 8,
            },
        )
        assert res.status_code == 201
        run_data = res.json()["run"]
        run_id = run_data["id"]

        res = await client.get(f"/api/benchmark/runs/{run_id}")
        assert res.status_code == 200
        assert res.json()["games_won"] == 14

        # 7. Delete / Close Game
        res = await client.delete(f"/api/games/{session_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "closed"


@pytest.mark.asyncio
async def test_session_concurrency():
    """Verify multiple independent game sessions can run without interference."""
    manager = SessionManager()
    session_1 = await manager.create_session(
        session_id="conc_sess_1",
        goal_text="Promote pawn to knight",
        mode="interactive",
    )
    session_2 = await manager.create_session(
        session_id="conc_sess_2",
        goal_text="Sacrifice rook",
        mode="benchmark",
    )

    try:
        # Move in session 1
        res1 = await session_1.execute_player_move("e2e4")
        assert res1["status"] == "ok"

        # Verify session 2 board untouched
        assert session_2.board.ply == 0
        assert session_1.board.ply == 1

        # Move in session 2
        res2 = await session_2.execute_player_move("d2d4")
        assert res2["status"] == "ok"
        assert session_2.board.ply == 1

        # Verify distinct FENs
        assert session_1.board.fen != session_2.board.fen
    finally:
        await manager.close_session("conc_sess_1")
        await manager.close_session("conc_sess_2")


def test_websocket_streaming():
    """Verify WebSocket bi-directional streaming and event handling."""
    from starlette.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/ws/game/test_ws_session_456") as ws:
            # 1. First event should be SYNC_STATE
            init_msg = ws.receive_json()
            assert init_msg["type"] == "SYNC_STATE"
            assert init_msg["session_id"] == "test_ws_session_456"
            assert "payload" in init_msg
            assert init_msg["payload"]["fen"] == chess.STARTING_FEN

            # 2. Send PLAYER_MOVE
            ws.send_json({"type": "PLAYER_MOVE", "payload": {"move": "e2e4"}})
            # Should receive BOARD_STATE, FEASIBILITY_CHANGE, MILESTONE_UPDATE
            events_received = []
            for _ in range(3):
                ev = ws.receive_json()
                events_received.append(ev["type"])

            assert "BOARD_STATE" in events_received
            assert "FEASIBILITY_CHANGE" in events_received

            # 3. Send PAUSE and RESUME
            ws.send_json({"type": "PAUSE", "payload": {}})
            pause_resp = ws.receive_json()
            assert pause_resp["type"] == "GAME_PAUSED"

            ws.send_json({"type": "RESUME", "payload": {}})
            resume_resp = ws.receive_json()
            assert resume_resp["type"] == "GAME_RESUMED"

            # 4. Test SYNC state snapshot
            ws.send_json({"type": "SYNC", "payload": {"last_seq": 0}})
            sync_resp = ws.receive_json()
            assert sync_resp["type"] == "SYNC_STATE"
            assert sync_resp["payload"]["fen"] == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


@pytest.mark.asyncio
async def test_game_session_step_with_mission_planner():
    """Verify live integration between GameSession, Stockfish engine, and MissionPlanner."""
    session = GameSession(
        session_id="session_planner_step_test",
        goal_text="Promote surviving pawns into knights",
        mode="interactive",
        machiavelli_color=chess.WHITE,
    )
    await session.initialize()

    events_received = []
    session.add_listener(lambda ev: events_received.append(ev))

    try:
        # Step turn for Machiavelli (White)
        step_res = await session.step_turn()
        assert step_res["status"] == "ok"
        assert step_res["player"] == "machiavelli"
        assert "move" in step_res
        assert session.board.ply == 1

        # Check broadcast events
        event_types = [ev["type"] for ev in events_received]
        assert "STOCKFISH_EVAL" in event_types
        assert "CANDIDATE_MOVES" in event_types
        assert "EXPLANATION" in event_types
        assert "BOARD_STATE" in event_types
        assert "FEASIBILITY_CHANGE" in event_types

        assert session.last_explanation is not None
        assert "explanation" in session.last_explanation
    finally:
        await session.close()
