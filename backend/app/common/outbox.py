from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event: str
    project_id: UUID
    payload: dict[str, Any]
