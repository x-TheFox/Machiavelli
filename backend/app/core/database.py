"""Database initialization and async session management for Machiavelli.

Supports SQLite via aiosqlite and SQLAlchemy 2.0.
"""

import os
from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

try:
    from backend.app.core.models import Base
except ImportError:
    from app.core.models import Base

# Database URL resolution with fallback
try:
    from backend.app.core.config import get_settings
    settings = get_settings()
    DATABASE_URL = getattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./machiavelli.db")
except Exception:
    try:
        from app.core.config import get_settings
        settings = get_settings()
        DATABASE_URL = getattr(settings, "DATABASE_URL", "sqlite+aiosqlite:///./machiavelli.db")
    except Exception:
        DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./machiavelli.db")

# Ensure SQLite path directory exists if a relative/absolute path is given
if "sqlite" in DATABASE_URL:
    db_path = DATABASE_URL.split("///")[-1]
    if db_path and db_path != ":memory:":
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

# Create async engine
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    future=True,
)

# Async session factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Enable foreign keys for SQLite
        if "sqlite" in DATABASE_URL:
            await conn.exec_driver_sql("PRAGMA foreign_keys = ON")
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining an asynchronous database session."""
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
