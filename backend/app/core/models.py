"""Machiavelli Core Database Models.

SQLAlchemy ORM models persisting game sessions, moves, milestones, and benchmark runs.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GameRecord(Base):
    __tablename__ = "game_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    goal_text: Mapped[str] = mapped_column(Text, default="")
    mode: Mapped[str] = mapped_column(String(32), default="interactive")  # interactive | benchmark
    status: Mapped[str] = mapped_column(
        String(32), default="active"
    )  # active, completed, impossible, resigned, draw, interrupted
    fen: Mapped[str] = mapped_column(String(128))
    start_fen: Mapped[str] = mapped_column(String(128))
    pgn: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 1-0, 0-1, 1/2-1/2, *
    termination_reason: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    machiavelli_color: Mapped[str] = mapped_column(String(16), default="white")
    opponent_type: Mapped[str] = mapped_column(String(32), default="stockfish")  # stockfish | human
    opponent_elo: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    moves_count: Mapped[int] = mapped_column(Integer, default=0)
    objective_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    objective_failed: Mapped[bool] = mapped_column(Boolean, default=False)
    impossibility_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    moves: Mapped[List["MoveRecord"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        order_by="MoveRecord.ply",
        lazy="selectin",
    )
    milestones: Mapped[List["MilestoneRecord"]] = relationship(
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> Dict[str, Any]:
        meta = {}
        if self.metadata_json:
            try:
                meta = json.loads(self.metadata_json)
            except Exception:
                meta = {"raw": self.metadata_json}

        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "goal_text": self.goal_text,
            "mode": self.mode,
            "status": self.status,
            "fen": self.fen,
            "start_fen": self.start_fen,
            "pgn": self.pgn,
            "result": self.result,
            "termination_reason": self.termination_reason,
            "machiavelli_color": self.machiavelli_color,
            "opponent_type": self.opponent_type,
            "opponent_elo": self.opponent_elo,
            "moves_count": self.moves_count,
            "objective_completed": self.objective_completed,
            "objective_failed": self.objective_failed,
            "impossibility_evidence": self.impossibility_evidence,
            "metadata": meta,
            "moves": [m.to_dict() for m in self.moves] if self.moves else [],
            "milestones": [m.to_dict() for m in self.milestones] if self.milestones else [],
        }


class MoveRecord(Base):
    __tablename__ = "move_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("game_records.id", ondelete="CASCADE"), index=True
    )
    move_number: Mapped[int] = mapped_column(Integer)
    ply: Mapped[int] = mapped_column(Integer)
    uci: Mapped[str] = mapped_column(String(16))
    san: Mapped[str] = mapped_column(String(16))
    player: Mapped[str] = mapped_column(String(32))  # "machiavelli" | "opponent"
    fen_before: Mapped[str] = mapped_column(String(128))
    fen_after: Mapped[str] = mapped_column(String(128))
    stockfish_eval_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stockfish_eval_mate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    goal_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_sacrifice: Mapped[bool] = mapped_column(Boolean, default=False)
    sacrifice_piece: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sacrifice_target_milestone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    decision_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    candidate_moves_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    game: Mapped["GameRecord"] = relationship(back_populates="moves")

    def to_dict(self) -> Dict[str, Any]:
        candidates = []
        if self.candidate_moves_json:
            try:
                candidates = json.loads(self.candidate_moves_json)
            except Exception:
                candidates = []

        return {
            "id": self.id,
            "game_id": self.game_id,
            "move_number": self.move_number,
            "ply": self.ply,
            "uci": self.uci,
            "san": self.san,
            "player": self.player,
            "fen_before": self.fen_before,
            "fen_after": self.fen_after,
            "stockfish_eval_cp": self.stockfish_eval_cp,
            "stockfish_eval_mate": self.stockfish_eval_mate,
            "goal_score": self.goal_score,
            "is_sacrifice": self.is_sacrifice,
            "sacrifice_piece": self.sacrifice_piece,
            "sacrifice_target_milestone": self.sacrifice_target_milestone,
            "decision_explanation": self.decision_explanation,
            "candidate_moves": candidates,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MilestoneRecord(Base):
    __tablename__ = "milestone_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("game_records.id", ondelete="CASCADE"), index=True
    )
    milestone_id: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32), default="pending"
    )  # pending, active, completed, failed
    target_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    target_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completed_at_ply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    game: Mapped["GameRecord"] = relationship(back_populates="milestones")

    def to_dict(self) -> Dict[str, Any]:
        details = {}
        if self.details_json:
            try:
                details = json.loads(self.details_json)
            except Exception:
                details = {"raw": self.details_json}

        return {
            "id": self.id,
            "game_id": self.game_id,
            "milestone_id": self.milestone_id,
            "description": self.description,
            "status": self.status,
            "target_type": self.target_type,
            "target_count": self.target_count,
            "current_count": self.current_count,
            "completed_at_ply": self.completed_at_ply,
            "details": details,
        }


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    tier_name: Mapped[str] = mapped_column(String(64))  # tier_1650, tier_1950, tier_2250
    engine_name: Mapped[str] = mapped_column(String(64), default="Stockfish 19")
    opponent_elo: Mapped[int] = mapped_column(Integer)
    total_games: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    games_drawn: Mapped[int] = mapped_column(Integer, default=0)
    games_lost: Mapped[int] = mapped_column(Integer, default=0)
    objective_completed_count: Mapped[int] = mapped_column(Integer, default=0)
    objective_failed_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_moves: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        config = {}
        if self.config_json:
            try:
                config = json.loads(self.config_json)
            except Exception:
                config = {"raw": self.config_json}

        results = {}
        if self.results_json:
            try:
                results = json.loads(self.results_json)
            except Exception:
                results = {"raw": self.results_json}

        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tier_name": self.tier_name,
            "engine_name": self.engine_name,
            "opponent_elo": self.opponent_elo,
            "total_games": self.total_games,
            "games_won": self.games_won,
            "games_drawn": self.games_drawn,
            "games_lost": self.games_lost,
            "objective_completed_count": self.objective_completed_count,
            "objective_failed_count": self.objective_failed_count,
            "avg_moves": self.avg_moves,
            "avg_nodes": self.avg_nodes,
            "config": config,
            "results": results,
        }
