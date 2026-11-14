"""Machiavelli Benchmarking Suite.

Provides standardized opening repertoires, calibrated Stockfish tournament runner,
comprehensive performance and objective metrics, baseline comparisons, and PGN exporters.
"""

from app.benchmark.openings import Opening, get_openings, get_opening_by_eco, get_opening_by_name
from app.benchmark.metrics import GameMetric, TournamentSummary, export_to_json, export_to_csv, export_to_pgn
from app.benchmark.tournament import TournamentConfig, TournamentRunner
from app.benchmark.baseline_compare import BaselineComparisonRunner

__all__ = [
    "Opening",
    "get_openings",
    "get_opening_by_eco",
    "get_opening_by_name",
    "GameMetric",
    "TournamentSummary",
    "export_to_json",
    "export_to_csv",
    "export_to_pgn",
    "TournamentConfig",
    "TournamentRunner",
    "BaselineComparisonRunner",
]
