import os
import shutil
from functools import lru_cache
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_stockfish_path() -> str:
    env_path = os.getenv("STOCKFISH_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    which_path = shutil.which("stockfish")
    if which_path and os.path.exists(which_path):
        return which_path
    if os.path.exists("/opt/homebrew/bin/stockfish"):
        return "/opt/homebrew/bin/stockfish"
    if os.path.exists("/usr/local/bin/stockfish"):
        return "/usr/local/bin/stockfish"
    if os.path.exists("/usr/bin/stockfish"):
        return "/usr/bin/stockfish"
    return "/opt/homebrew/bin/stockfish"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    STOCKFISH_PATH: str = Field(default_factory=_resolve_stockfish_path)
    STOCKFISH_THREADS: int = 2
    STOCKFISH_HASH: int = 64
    DEFAULT_SEARCH_DEPTH: int = 6
    DEFAULT_SEARCH_MOVETIME_MS: int = 1000
    DEFAULT_MULTIPV: int = 5

    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    DATABASE_URL: str = "sqlite+aiosqlite:///./machiavelli.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["*"]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
