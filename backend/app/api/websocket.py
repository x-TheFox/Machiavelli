"""WebSocket Streaming & Client Protocol for Project Machiavelli.

Provides real-time bi-directional streaming of:
- BOARD_STATE
- CANDIDATE_MOVES
- STOCKFISH_EVAL
- MILESTONE_UPDATE
- FEASIBILITY_CHANGE
- EXPLANATION
- FALLBACK_PROMPT
- GAME_OVER

Supports monotonic sequence-number tracking, reconnection synchronization,
and multi-client broadcasting per game session.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Set

import chess
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.chess_engine.game_session import GameSession, session_manager

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["Machiavelli WebSocket"])


class ConnectionManager:
    """Manages active WebSockets grouped by session ID."""

    def __init__(self):
        self._active_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accept WebSocket and register under session_id."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._active_connections:
                self._active_connections[session_id] = set()
            self._active_connections[session_id].add(websocket)
        logger.info(f"WebSocket connected for session {session_id} (total: {len(self._active_connections[session_id])})")

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove WebSocket on disconnect."""
        async with self._lock:
            if session_id in self._active_connections:
                self._active_connections[session_id].discard(websocket)
                if not self._active_connections[session_id]:
                    del self._active_connections[session_id]
        logger.info(f"WebSocket disconnected for session {session_id}")

    async def send_to_socket(self, websocket: WebSocket, event: Dict[str, Any]) -> None:
        """Send JSON payload safely to a single socket."""
        try:
            await websocket.send_json(event)
        except Exception as e:
            logger.debug(f"Failed to send to socket: {e}")

    async def broadcast_to_session(self, session_id: str, event: Dict[str, Any]) -> None:
        """Broadcast payload to all active websockets in a session."""
        async with self._lock:
            sockets = list(self._active_connections.get(session_id, set()))

        for ws in sockets:
            await self.send_to_socket(ws, event)


conn_manager = ConnectionManager()


@ws_router.websocket("/ws/game/{session_id}")
async def game_websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Main WebSocket endpoint for game interaction and live streaming.
    Path: /ws/game/{session_id}
    """
    await conn_manager.connect(session_id, websocket)

    # Fetch or auto-create session
    session = await session_manager.get_session(session_id)
    if not session:
        session = await session_manager.create_session(
            session_id=session_id,
            goal_text="",
            mode="interactive",
        )

    # Callback listener for session broadcast events
    async def session_event_listener(event: Dict[str, Any]):
        await conn_manager.send_to_socket(websocket, event)

    session.add_listener(session_event_listener)

    try:
        # Send initial full state snapshot and current seq
        initial_state = session.get_state_snapshot()
        await websocket.send_json({
            "type": "SYNC_STATE",
            "session_id": session_id,
            "seq": session.seq,
            "payload": initial_state,
        })

        while True:
            # Receive client message
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                await websocket.send_json({
                    "type": "ERROR",
                    "payload": {"message": "Invalid JSON message"},
                })
                continue

            msg_type = msg.get("type", "").upper()
            payload = msg.get("payload", {})

            # -------------------------------------------------------------
            # Client Action Handlers
            # -------------------------------------------------------------

            if msg_type == "SYNC":
                # Reconnection state catch-up
                last_seq = payload.get("last_seq", 0)
                if last_seq > 0 and last_seq <= session.seq:
                    missed_events = session.get_events_since(last_seq)
                    for ev in missed_events:
                        await websocket.send_json(ev)
                else:
                    # Provide complete state snapshot
                    await websocket.send_json({
                        "type": "SYNC_STATE",
                        "session_id": session_id,
                        "seq": session.seq,
                        "payload": session.get_state_snapshot(),
                    })

            elif msg_type == "START_GAME":
                goal_text = payload.get("goal", payload.get("goal_text", ""))
                mode = payload.get("mode", "interactive")
                color_str = payload.get("color", "white").lower()
                elo = payload.get("elo", 1950)
                start_fen = payload.get("start_fen")

                color = chess.WHITE if color_str == "white" else chess.BLACK

                # Close previous session engine and re-initialize
                await session_manager.close_session(session_id)
                session = await session_manager.create_session(
                    session_id=session_id,
                    goal_text=goal_text,
                    mode=mode,
                    machiavelli_color=color,
                    opponent_elo=elo,
                    start_fen=start_fen,
                )
                session.add_listener(session_event_listener)

                await websocket.send_json({
                    "type": "GAME_STARTED",
                    "session_id": session_id,
                    "payload": session.get_state_snapshot(),
                })

                # If Machiavelli plays White, auto-trigger first move
                if session.machiavelli_color == chess.WHITE and not session.board.is_game_over():
                    asyncio.create_task(session.step_turn())

            elif msg_type == "PLAYER_MOVE":
                move_str = payload.get("move", "")
                res = await session.execute_player_move(move_str)
                if res.get("status") == "error":
                    await websocket.send_json({
                        "type": "MOVE_ERROR",
                        "payload": {"message": res.get("message")},
                    })
                else:
                    # If move succeeded and next turn is Machiavelli, auto-step
                    if session.board.turn == session.machiavelli_color and not session.board.is_game_over():
                        asyncio.create_task(session.step_turn())

            elif msg_type in {"STEP", "ENGINE_MOVE"}:
                asyncio.create_task(session.step_turn())

            elif msg_type == "FALLBACK_CHOICE":
                choice = payload.get("choice", "")
                params = payload.get("params")
                res = await session.handle_fallback_choice(choice, params)
                if res.get("status") == "error":
                    await websocket.send_json({
                        "type": "ERROR",
                        "payload": {"message": res.get("message")},
                    })
                else:
                    # If resolved and it's our turn, resume stepping
                    if not session.is_paused and not session.board.is_game_over():
                        if session.board.turn == session.machiavelli_color:
                            asyncio.create_task(session.step_turn())

            elif msg_type == "PAUSE":
                session.is_paused = True
                await session.broadcast_event("GAME_PAUSED", {"session_id": session_id})

            elif msg_type == "RESUME":
                session.is_paused = False
                await session.broadcast_event("GAME_RESUMED", {"session_id": session_id})
                if not session.board.is_game_over():
                    asyncio.create_task(session.step_turn())

            elif msg_type == "RESET":
                start_fen = payload.get("start_fen", chess.STARTING_FEN)
                await session_manager.close_session(session_id)
                session = await session_manager.create_session(
                    session_id=session_id,
                    goal_text=session.raw_goal_text,
                    mode=session.mode,
                    machiavelli_color=session.machiavelli_color,
                    opponent_elo=session.opponent_elo,
                    start_fen=start_fen,
                )
                session.add_listener(session_event_listener)
                await websocket.send_json({
                    "type": "GAME_RESET",
                    "session_id": session_id,
                    "payload": session.get_state_snapshot(),
                })

            else:
                logger.warning(f"Unknown WebSocket message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from session {session_id}")
    except Exception as e:
        logger.error(f"WebSocket exception in session {session_id}: {e}", exc_info=True)
    finally:
        session.remove_listener(session_event_listener)
        await conn_manager.disconnect(session_id, websocket)
