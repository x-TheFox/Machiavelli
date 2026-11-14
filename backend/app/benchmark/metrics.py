"""Machiavelli Benchmark Metrics and Exporters.

Provides data structures, computation routines, and export facilities (JSON, CSV, PGN, Markdown)
for tournament performance, objective completion rates, blunder analysis, and Elo tier breakdowns.
"""

import csv
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class GameMetric:
    """Individual match metric record."""
    game_id: str
    tier_name: str
    opponent_elo: int
    opening_eco: str
    opening_name: str
    machiavelli_color: str  # "white" | "black"
    result: str  # "1-0" | "0-1" | "1/2-1/2" | "*"
    machiavelli_result: str  # "win" | "loss" | "draw" | "interrupted"
    objective_completed: bool = False
    modified_objective_completed: bool = False
    blunders: int = 0
    total_moves: int = 0
    total_plies: int = 0
    moves_to_completion: Optional[int] = None
    avg_move_time_ms: float = 0.0
    avg_eval_cp: float = 0.0
    sacrifices_count: int = 0
    promotions_count: int = 0
    termination_reason: str = "normal"
    pgn_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TierSummary:
    """Aggregated metrics for an individual Elo tier."""
    tier_name: str
    opponent_elo: int
    total_games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    win_rate: float = 0.0
    draw_rate: float = 0.0
    loss_rate: float = 0.0
    objective_completed_count: int = 0
    objective_completion_rate: float = 0.0
    modified_objective_count: int = 0
    modified_objective_rate: float = 0.0
    total_blunders: int = 0
    avg_blunders_per_game: float = 0.0
    avg_moves: float = 0.0
    avg_moves_to_completion: Optional[float] = None
    avg_move_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TournamentSummary:
    """Aggregated metrics across the entire tournament."""
    total_games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    win_rate: float = 0.0
    draw_rate: float = 0.0
    loss_rate: float = 0.0
    objective_completed_count: int = 0
    objective_completion_rate: float = 0.0
    modified_objective_count: int = 0
    modified_objective_rate: float = 0.0
    total_blunders: int = 0
    avg_blunders_per_game: float = 0.0
    avg_moves: float = 0.0
    avg_moves_to_completion: Optional[float] = None
    avg_move_time_ms: float = 0.0
    tier_breakdown: Dict[str, TierSummary] = field(default_factory=dict)
    hardware_info: Dict[str, str] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["tier_breakdown"] = {
            k: v.to_dict() if hasattr(v, "to_dict") else v
            for k, v in self.tier_breakdown.items()
        }
        return res


def get_system_hardware_info() -> Dict[str, str]:
    """Capture environment and hardware details for benchmark reproducibility."""
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python_version": sys.version.split()[0],
        "cpu_count": str(os.cpu_count() or 1),
    }


def compute_blunder_count(
    eval_history: List[Dict[str, Any]],
    machiavelli_color: str = "white",
    blunder_threshold_cp: int = 200,
) -> int:
    """Compute blunder count on Machiavelli turns.
    
    A move is classified as a blunder ONLY if:
    1. It was made on Machiavelli's turn.
    2. The centipawn evaluation dropped by >= blunder_threshold_cp.
    3. The move was NOT an intentional tagged sacrifice targeting a milestone.
    """
    blunders = 0
    is_white = machiavelli_color.lower() == "white"

    for i in range(1, len(eval_history)):
        prev = eval_history[i - 1]
        curr = eval_history[i]
        
        # Check if this move was played by Machiavelli
        player = curr.get("player", "")
        if player != "machiavelli":
            continue

        # If it was an intentional sacrifice, it is strictly NOT a blunder
        if curr.get("is_sacrifice", False):
            continue

        prev_cp = prev.get("eval_cp")
        curr_cp = curr.get("eval_cp")
        if prev_cp is None or curr_cp is None:
            continue

        # For White, score drop is prev_cp - curr_cp
        # For Black, score drop is curr_cp - prev_cp (from Black's perspective)
        drop = (prev_cp - curr_cp) if is_white else (curr_cp - prev_cp)
        if drop >= blunder_threshold_cp:
            blunders += 1

    return blunders


def compute_tier_summary(games: List[GameMetric], tier_name: str, elo: int) -> TierSummary:
    """Aggregate metrics for a specific Elo tier."""
    if not games:
        return TierSummary(tier_name=tier_name, opponent_elo=elo)

    n = len(games)
    wins = sum(1 for g in games if g.machiavelli_result == "win")
    draws = sum(1 for g in games if g.machiavelli_result == "draw")
    losses = sum(1 for g in games if g.machiavelli_result == "loss")
    obj_completed = sum(1 for g in games if g.objective_completed)
    mod_obj_completed = sum(1 for g in games if g.modified_objective_completed)
    total_blunders = sum(g.blunders for g in games)
    total_moves = sum(g.total_moves for g in games)
    total_time = sum(g.avg_move_time_ms for g in games)

    completion_moves = [g.moves_to_completion for g in games if g.objective_completed and g.moves_to_completion is not None]
    avg_moves_to_comp = (sum(completion_moves) / len(completion_moves)) if completion_moves else None

    return TierSummary(
        tier_name=tier_name,
        opponent_elo=elo,
        total_games=n,
        wins=wins,
        draws=draws,
        losses=losses,
        win_rate=round(wins / n, 4),
        draw_rate=round(draws / n, 4),
        loss_rate=round(losses / n, 4),
        objective_completed_count=obj_completed,
        objective_completion_rate=round(obj_completed / n, 4),
        modified_objective_count=mod_obj_completed,
        modified_objective_rate=round(mod_obj_completed / n, 4),
        total_blunders=total_blunders,
        avg_blunders_per_game=round(total_blunders / n, 2),
        avg_moves=round(total_moves / n, 1),
        avg_moves_to_completion=round(avg_moves_to_comp, 1) if avg_moves_to_comp is not None else None,
        avg_move_time_ms=round(total_time / n, 1),
    )


def compute_tournament_summary(
    games: List[GameMetric],
    hardware_info: Optional[Dict[str, str]] = None,
) -> TournamentSummary:
    """Aggregate metrics across all tournament games and group by tier."""
    if not games:
        return TournamentSummary(hardware_info=hardware_info or get_system_hardware_info())

    n = len(games)
    wins = sum(1 for g in games if g.machiavelli_result == "win")
    draws = sum(1 for g in games if g.machiavelli_result == "draw")
    losses = sum(1 for g in games if g.machiavelli_result == "loss")
    obj_completed = sum(1 for g in games if g.objective_completed)
    mod_obj_completed = sum(1 for g in games if g.modified_objective_completed)
    total_blunders = sum(g.blunders for g in games)
    total_moves = sum(g.total_moves for g in games)
    total_time = sum(g.avg_move_time_ms for g in games)

    completion_moves = [g.moves_to_completion for g in games if g.objective_completed and g.moves_to_completion is not None]
    avg_moves_to_comp = (sum(completion_moves) / len(completion_moves)) if completion_moves else None

    # Group by tier
    tier_groups: Dict[str, List[GameMetric]] = {}
    tier_elos: Dict[str, int] = {}
    for g in games:
        tier_groups.setdefault(g.tier_name, []).append(g)
        tier_elos[g.tier_name] = g.opponent_elo

    tier_breakdown: Dict[str, TierSummary] = {}
    for tier_name, tier_games in tier_groups.items():
        tier_breakdown[tier_name] = compute_tier_summary(
            tier_games, tier_name, tier_elos[tier_name]
        )

    return TournamentSummary(
        total_games=n,
        wins=wins,
        draws=draws,
        losses=losses,
        win_rate=round(wins / n, 4),
        draw_rate=round(draws / n, 4),
        loss_rate=round(losses / n, 4),
        objective_completed_count=obj_completed,
        objective_completion_rate=round(obj_completed / n, 4),
        modified_objective_count=mod_obj_completed,
        modified_objective_rate=round(mod_obj_completed / n, 4),
        total_blunders=total_blunders,
        avg_blunders_per_game=round(total_blunders / n, 2),
        avg_moves=round(total_moves / n, 1),
        avg_moves_to_completion=round(avg_moves_to_comp, 1) if avg_moves_to_comp is not None else None,
        avg_move_time_ms=round(total_time / n, 1),
        tier_breakdown=tier_breakdown,
        hardware_info=hardware_info or get_system_hardware_info(),
    )


def export_to_json(summary: TournamentSummary, games: List[GameMetric], filepath: str) -> None:
    """Export complete tournament results and game metrics to JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    payload = {
        "summary": summary.to_dict(),
        "games": [g.to_dict() for g in games],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def export_to_csv(games: List[GameMetric], filepath: str) -> None:
    """Export game metrics to CSV for tabular analysis."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    if not games:
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            f.write("game_id,tier_name,opponent_elo,opening_eco,machiavelli_color,result,machiavelli_result,objective_completed,blunders,total_moves\n")
        return

    fieldnames = [
        "game_id",
        "tier_name",
        "opponent_elo",
        "opening_eco",
        "opening_name",
        "machiavelli_color",
        "result",
        "machiavelli_result",
        "objective_completed",
        "modified_objective_completed",
        "blunders",
        "total_moves",
        "total_plies",
        "moves_to_completion",
        "avg_move_time_ms",
        "avg_eval_cp",
        "sacrifices_count",
        "promotions_count",
        "termination_reason",
    ]
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for g in games:
            writer.writerow(g.to_dict())


def export_to_pgn(games: List[GameMetric], filepath: str) -> None:
    """Export all game PGNs into a single combined PGN file."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for g in games:
            if g.pgn_text:
                f.write(g.pgn_text.strip())
                f.write("\n\n")


def generate_markdown_report(summary: TournamentSummary) -> str:
    """Generate an executive Markdown summary report."""
    lines = [
        "# Machiavelli Benchmark Tournament Report",
        "",
        f"**Timestamp (UTC):** {summary.timestamp}",
        f"**Total Matches:** {summary.total_games}",
        f"**Overall Record (W-D-L):** {summary.wins}-{summary.draws}-{summary.losses} ({summary.win_rate * 100:.1f}%)",
        f"**Objective Completion Rate:** {summary.objective_completion_rate * 100:.1f}% ({summary.objective_completed_count}/{summary.total_games})",
        f"**Modified Objective Rate:** {summary.modified_objective_rate * 100:.1f}%",
        f"**Tactical Blunders / Game:** {summary.avg_blunders_per_game:.2f}",
        f"**Average Moves / Game:** {summary.avg_moves:.1f}",
    ]
    if summary.avg_moves_to_completion is not None:
        lines.append(f"**Average Moves to Objective Completion:** {summary.avg_moves_to_completion:.1f}")

    lines.extend([
        "",
        "## Performance by Calibrated Stockfish Elo Tier",
        "",
        "| Tier | Elo | Games | Record (W-D-L) | Win % | Obj Complete % | Blunders/Game | Avg Moves |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])

    for tier_name, tier in sorted(summary.tier_breakdown.items(), key=lambda x: x[1].opponent_elo):
        lines.append(
            f"| {tier.tier_name} | {tier.opponent_elo} | {tier.total_games} | "
            f"{tier.wins}-{tier.draws}-{tier.losses} | {tier.win_rate * 100:.1f}% | "
            f"{tier.objective_completion_rate * 100:.1f}% | {tier.avg_blunders_per_game:.2f} | "
            f"{tier.avg_moves:.1f} |"
        )

    lines.extend([
        "",
        "## Hardware & Environment Specification",
        "",
        f"- **Platform:** {summary.hardware_info.get('platform', 'N/A')}",
        f"- **Processor:** {summary.hardware_info.get('processor', 'N/A')}",
        f"- **CPU Count:** {summary.hardware_info.get('cpu_count', 'N/A')}",
        f"- **Python Version:** {summary.hardware_info.get('python_version', 'N/A')}",
        "",
    ])

    return "\n".join(lines)
