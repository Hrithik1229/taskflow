from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Comment cannot be empty.")
        return normalized


class CommentAuthor(BaseModel):
    id: UUID
    username: str

    model_config = ConfigDict(from_attributes=True)


class CommentRead(BaseModel):
    id: UUID
    task_id: UUID
    content: str
    author: CommentAuthor
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class CommentListResponse(BaseModel):
    items: list[CommentRead]
    total: int
    limit: int
    offset: int
