"""Main FastAPI application for Project Machiavelli.

Orchestrates REST API, WebSocket streams, CORS middleware, and DB lifecycle.
"""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.routes import router
from backend.app.api.websocket import ws_router
from backend.app.chess_engine.game_session import session_manager
from backend.app.core.config import settings
from backend.app.core.database import init_db

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("machiavelli")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context for startup and shutdown procedures."""
    logger.info("Starting Project Machiavelli backend service...")
    try:
        await init_db()
        logger.info("SQLite database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error during database initialization: {e}", exc_info=True)

    yield

    logger.info("Shutting down Project Machiavelli backend service...")
    active_sessions = await session_manager.list_active_sessions()
    for s in active_sessions:
        try:
            await session_manager.close_session(s["session_id"])
        except Exception as e:
            logger.warning(f"Error closing session {s['session_id']}: {e}")
    logger.info("Cleanup complete.")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    application = FastAPI(
        title="Machiavelli Chess Intelligence API",
        description=(
            "Autonomous goal-conditioned chess intelligence system built around Stockfish, "
            "adversarial search planning, and formal constraint verification."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # Configure CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include REST and WebSocket routers
    application.include_router(router)
    application.include_router(ws_router)

    @application.get("/")
    async def root():
        return {
            "name": "Machiavelli Autonomous Chess Engine API",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/health",
        }

    return application


app = create_app()
