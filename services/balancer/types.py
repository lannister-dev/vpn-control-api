from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class NodeLoad:
    node_id: UUID
    name: str
    bps: float
    sessions: int
    cpu_pct: float
    capacity: float


@dataclass(frozen=True)
class KeyLoad:
    key_id: UUID
    bps: float
    current_backend_id: UUID | None
    eligible_backend_ids: frozenset[UUID]


@dataclass(frozen=True)
class Move:
    key_id: UUID
    from_backend_id: UUID | None
    to_backend_id: UUID
    to_tag: str
    bps: float


@dataclass(frozen=True)
class BalancePlan:
    moves: list[Move] = field(default_factory=list)
    deviations: dict[UUID, float] = field(default_factory=dict)
    skipped_reason: str | None = None

    @property
    def is_noop(self) -> bool:
        return not self.moves
