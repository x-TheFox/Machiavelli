from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FeasibilityStatus(str, Enum):
    FEASIBLE = "FEASIBLE"
    AT_RISK = "AT_RISK"
    UNRESOLVED = "UNRESOLVED"
    PROVEN_IMPOSSIBLE = "PROVEN_IMPOSSIBLE"
    COMPLETED = "COMPLETED"


class MilestoneType(str, Enum):
    SACRIFICE_PIECE = "SACRIFICE_PIECE"
    SACRIFICE_ALL_ORIGINAL_PIECES = "SACRIFICE_ALL_ORIGINAL_PIECES"
    SACRIFICE_QUEEN = "SACRIFICE_QUEEN"
    PROMOTE_PAWN = "PROMOTE_PAWN"
    PROMOTE_SURVIVING_PAWNS = "PROMOTE_SURVIVING_PAWNS"
    PROMOTE_ALL_8_PAWNS = "PROMOTE_ALL_8_PAWNS"
    CHECKMATE_WITH_PIECE = "CHECKMATE_WITH_PIECE"
    WIN_GAME = "WIN_GAME"
    CUSTOM = "CUSTOM"


class MilestoneStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Milestone(BaseModel):
    id: str
    title: str
    description: str
    milestone_type: MilestoneType
    target_piece_types: List[str] = Field(default_factory=list)
    target_piece_ids: List[str] = Field(default_factory=list)
    target_count: int = 1
    current_count: int = 0
    status: MilestoneStatus = MilestoneStatus.PENDING
    dependencies: List[str] = Field(default_factory=list)
    conditions: Dict[str, Any] = Field(default_factory=dict)

    def is_active(self) -> bool:
        return self.status == MilestoneStatus.ACTIVE

    def is_completed(self) -> bool:
        return self.status == MilestoneStatus.COMPLETED

    def is_failed(self) -> bool:
        return self.status == MilestoneStatus.FAILED

    def is_pending(self) -> bool:
        return self.status == MilestoneStatus.PENDING

    @property
    def progress_ratio(self) -> float:
        if self.target_count <= 0:
            return 1.0 if self.is_completed() else 0.0
        return min(1.0, max(0.0, float(self.current_count) / float(self.target_count)))


class Invariant(BaseModel):
    id: str
    name: str
    description: str
    max_our_captures: Optional[int] = None
    max_moves: Optional[int] = None
    no_pawn_losses: bool = False
    disallowed_piece_types: List[str] = Field(default_factory=list)
    protected_piece_ids: List[str] = Field(default_factory=list)
    custom_rules: Dict[str, Any] = Field(default_factory=dict)


class FeasibilityReport(BaseModel):
    status: FeasibilityStatus
    reason: str
    broken_invariant_id: Optional[str] = None
    failed_milestone_id: Optional[str] = None
    threatened_entities: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class GoalDefinition(BaseModel):
    goal_id: str
    raw_instruction: str
    color: str = "white"  # "white" or "black"
    title: str
    description: str
    milestones: List[Milestone] = Field(default_factory=list)
    invariants: List[Invariant] = Field(default_factory=list)
    active_milestone_id: Optional[str] = None
    feasibility_status: FeasibilityStatus = FeasibilityStatus.FEASIBLE
    status_reason: str = "Initial plan generated"
    is_ambiguous: bool = False
    clarification_prompt: Optional[str] = None

    def get_milestone(self, milestone_id: str) -> Optional[Milestone]:
        for m in self.milestones:
            if m.id == milestone_id:
                return m
        return None

    def get_active_milestones(self) -> List[Milestone]:
        return [m for m in self.milestones if m.status == MilestoneStatus.ACTIVE]

    def get_pending_milestones(self) -> List[Milestone]:
        return [m for m in self.milestones if m.status == MilestoneStatus.PENDING]

    def get_completed_milestones(self) -> List[Milestone]:
        return [m for m in self.milestones if m.status == MilestoneStatus.COMPLETED]

    def is_all_completed(self) -> bool:
        return len(self.milestones) > 0 and all(m.is_completed() for m in self.milestones)

    def validate_dag(self) -> bool:
        """Validate DAG: check that all dependency IDs exist and there are no cycles."""
        all_ids = {m.id for m in self.milestones}
        for m in self.milestones:
            for dep in m.dependencies:
                if dep not in all_ids:
                    return False

        # Cycle detection using DFS
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited

        def has_cycle(node_id: str) -> bool:
            visited[node_id] = 1
            node = self.get_milestone(node_id)
            if node:
                for dep in node.dependencies:
                    state = visited.get(dep, 0)
                    if state == 1:
                        return True
                    if state == 0 and has_cycle(dep):
                        return True
            visited[node_id] = 2
            return False

        for m in self.milestones:
            if visited.get(m.id, 0) == 0:
                if has_cycle(m.id):
                    return False
        return True

    def get_topological_order(self) -> List[str]:
        """Return milestone IDs in dependency order (dependencies first)."""
        adj: Dict[str, List[str]] = {m.id: [] for m in self.milestones}
        in_degree: Dict[str, int] = {m.id: 0 for m in self.milestones}

        for m in self.milestones:
            for dep in m.dependencies:
                if dep in adj:
                    adj[dep].append(m.id)
                    in_degree[m.id] += 1

        queue = [m_id for m_id, deg in in_degree.items() if deg == 0]
        order: List[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for nxt in adj.get(curr, []):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        return order

    def advance_dag(self) -> Optional[str]:
        """
        Advance active milestones:
        Any PENDING milestone whose dependencies are all COMPLETED transitions to ACTIVE.
        Returns the ID of the primary active milestone, or None if all completed.
        """
        completed_ids = {m.id for m in self.milestones if m.is_completed()}
        for m in self.milestones:
            if m.status == MilestoneStatus.PENDING:
                if all(dep in completed_ids for dep in m.dependencies):
                    m.status = MilestoneStatus.ACTIVE

        active = self.get_active_milestones()
        if active:
            self.active_milestone_id = active[0].id
            return active[0].id

        if self.is_all_completed():
            self.active_milestone_id = None
            self.feasibility_status = FeasibilityStatus.COMPLETED
            self.status_reason = "All milestones completed"
            return None

        return None
