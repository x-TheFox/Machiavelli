#!/usr/bin/env python3
"""Uvicorn server startup script for Project Machiavelli."""

import argparse
import os
import sys
from pathlib import Path

# Ensure workspace root and backend directory are in sys.path
backend_dir = Path(__file__).resolve().parent
repo_root = backend_dir.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import uvicorn
from backend.app.core.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run Machiavelli FastAPI backend server.")
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", settings.HOST),
        help=f"Host address to bind (default: {settings.HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", settings.PORT)),
        help=f"Port to bind (default: {settings.PORT})",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        default=settings.DEBUG,
        help="Enable auto-reload on file changes",
    )

    args = parser.parse_args()

    print(f"============================================================")
    print(f" Starting Project Machiavelli Server")
    print(f" Listening on http://{args.host}:{args.port}")
    print(f" OpenAPI Docs: http://{args.host}:{args.port}/docs")
    print(f" Stockfish binary: {settings.STOCKFISH_PATH}")
    print(f"============================================================")

    uvicorn.run(
        "backend.app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
