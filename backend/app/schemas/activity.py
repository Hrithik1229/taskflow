from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActivityActor(BaseModel):
    id: UUID
    username: str

    model_config = ConfigDict(from_attributes=True)


class ActivityRead(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str | None = None
    actor: ActivityActor
    action: str
    entity_type: str
    entity_id: UUID
    details: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityListResponse(BaseModel):
    items: list[ActivityRead]
    total: int
    limit: int
    offset: int
