#!/usr/bin/env python3
"""Machiavelli Tournament and Baseline Comparison CLI Command.

Executes calibrated tournaments against Stockfish (1650, 1950, 2250 Elo),
runs 4-way baseline comparisons (Unmodified Stockfish, GoalFish, Reranking, Full Planner),
and exports PGNs, CSVs, JSON summaries, and Markdown reports.

Usage:
    # Full tournament
    python backend/run_tournament.py --tiers 1650,1950,2250 --movetime 2000

    # Quick smoke test (CI / rapid check)
    python backend/run_tournament.py --quick

    # Baseline comparison (A vs B vs C vs D)
    python backend/run_tournament.py --baseline --quick
"""

import argparse
import asyncio
import os
import sys

# Ensure backend and root are in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.benchmark.openings import get_openings
from app.benchmark.tournament import TournamentConfig, TournamentRunner
from app.benchmark.baseline_compare import BaselineComparisonRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Machiavelli Tournament Benchmark Runner and Baseline Comparison CLI"
    )
    parser.add_argument(
        "--tiers",
        type=str,
        default="1650,1950,2250",
        help="Comma-separated list of Stockfish Elo tiers (e.g. '1650,1950,2250')",
    )
    parser.add_argument(
        "--games-per-opening",
        type=int,
        default=2,
        help="Number of games per opening (default 2: 1 as White, 1 as Black)",
    )
    parser.add_argument(
        "--movetime",
        type=int,
        default=2000,
        help="Search budget per move in milliseconds (default: 2000ms)",
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=100,
        help="Maximum full moves per game before cutoff (default: 100)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run quick smoke-test mode (1 tier, 2 openings, fast search)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run 4-way architectural baseline comparison (A vs B vs C vs D)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/benchmark",
        help="Directory to save benchmark reports and PGNs (default: reports/benchmark)",
    )
    parser.add_argument(
        "--stockfish-path",
        type=str,
        default=None,
        help="Optional explicit path to Stockfish binary",
    )
    parser.add_argument(
        "--objective",
        type=str,
        default=(
            "Sacrifice all original pieces, promote every surviving pawn into a knight, "
            "and checkmate using the promoted knights"
        ),
        help="Natural-language objective instruction for Machiavelli",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    print("=" * 70)
    print("           MACHIAVELLI BENCHMARK & TOURNAMENT ARENA            ")
    print("=" * 70)

    if args.baseline:
        print("\n[Mode] Running 4-Way Architectural Baseline Comparison")
        runner = BaselineComparisonRunner(
            stockfish_path=args.stockfish_path,
            movetime_ms=100 if args.quick else args.movetime,
            max_moves_per_game=10 if args.quick else args.max_moves,
        )
        test_openings = get_openings()[:1] if args.quick else get_openings()[:3]
        print(f"Evaluating {len(test_openings)} opening(s) across 4 baselines...")
        report = await runner.run_comparison(
            openings=test_openings,
            opponent_elo=1650,
            objective_instruction=args.objective,
        )

        md_content = report.to_markdown()
        print("\n" + md_content)

        os.makedirs(args.output_dir, exist_ok=True)
        report_path = os.path.join(args.output_dir, "baseline_comparison.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"\nBaseline comparison report saved to: {report_path}")
        return

    # Standard Tournament Run
    try:
        tiers = [int(t.strip()) for t in args.tiers.split(",") if t.strip()]
    except ValueError:
        print(f"Error: Invalid tiers format: {args.tiers}. Use e.g. '1650,1950,2250'")
        sys.exit(1)

    config = TournamentConfig(
        tiers=tiers,
        games_per_opening=args.games_per_opening,
        movetime_ms=args.movetime,
        max_moves=args.max_moves,
        output_dir=args.output_dir,
        stockfish_path=args.stockfish_path,
        objective_instruction=args.objective,
        quick_mode=args.quick,
    )

    runner = TournamentRunner(config)

    def print_progress(curr, total, elo, opening_name, color):
        color_str = "White" if color else "Black"
        print(f"[{curr:02d}/{total:02d}] Tier {elo} | Machiavelli as {color_str:5s} | Opening: {opening_name}")

    summary, games = await runner.run_tournament(progress_callback=print_progress)

    print("\n" + "=" * 70)
    print("                     TOURNAMENT COMPLETED                      ")
    print("=" * 70)
    print(f"Total Games Played: {summary.total_games}")
    print(f"Overall Record:     {summary.wins} Wins, {summary.draws} Draws, {summary.losses} Losses ({summary.win_rate * 100:.1f}%)")
    print(f"Objective Success:  {summary.objective_completion_rate * 100:.1f}% ({summary.objective_completed_count}/{summary.total_games})")
    print(f"Tactical Blunders:  {summary.avg_blunders_per_game:.2f} per game")
    print(f"Artifacts written to: {config.output_dir}/")
    print("  - tournament_results.json")
    print("  - tournament_games.csv")
    print("  - tournament_games.pgn")
    print("  - tournament_report.md")


if __name__ == "__main__":
    asyncio.run(main())
