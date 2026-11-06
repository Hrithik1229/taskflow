from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import TaskPriority, TaskStatus

SortField = Literal["status", "position", "created_at", "updated_at", "due_at", "title"]
SortDirection = Literal["asc", "desc"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: UUID | None = None
    due_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def require_review_submission(cls, value: TaskStatus) -> TaskStatus:
        if value == TaskStatus.REVIEW:
            raise ValueError("Create the task before moving it into Review.")
        return value

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Task title cannot be empty.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone.")
        return value.astimezone(UTC)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: TaskPriority | None = None
    assigned_to: UUID | None = None
    reviewer_id: UUID | None = None
    due_at: datetime | None = None
    expected_version: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Task title cannot be null.")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Task title cannot be empty.")
        return normalized

    @field_validator("priority")
    @classmethod
    def require_priority(cls, value: TaskPriority | None) -> TaskPriority:
        if value is None:
            raise ValueError("Task priority cannot be null.")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("due_at")
    @classmethod
    def require_aware_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_mutable_field(self) -> "TaskUpdate":
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("At least one task field must be provided.")
        return self


class TaskMove(BaseModel):
    status: TaskStatus
    position: int = Field(ge=0)
    expected_version: int = Field(ge=1)
    reviewer_id: UUID | None = None

    model_config = ConfigDict(extra="forbid")


class TaskUserSummary(BaseModel):
    id: UUID
    username: str

    model_config = ConfigDict(from_attributes=True)


class TaskRead(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assigned_to: UUID | None
    assignee: TaskUserSummary | None
    reviewer_id: UUID | None
    reviewer: TaskUserSummary | None
    review_requested_by: TaskUserSummary | None
    status_changed_by: TaskUserSummary | None
    status_changed_at: datetime | None
    completed_by: TaskUserSummary | None
    completed_at: datetime | None
    completed_by_removed: bool
    created_by: UUID
    creator: TaskUserSummary
    due_at: datetime | None
    position: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int


class TaskPosition(BaseModel):
    id: UUID
    position: int
    version: int


class TaskMoveResponse(BaseModel):
    task: TaskRead
    affected: list[TaskPosition]


class DashboardSummary(BaseModel):
    total_tasks: int
    assigned_to_me: int
    overdue: int
    completed: int


DashboardMetric = Literal["total", "overdue", "completed", "assigned_to_me"]


class DashboardBreakdownTask(BaseModel):
    id: UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    assignee: TaskUserSummary | None
    completed_by: TaskUserSummary | None = None
    completed_by_removed: bool = False


class DashboardProjectBreakdown(BaseModel):
    project_id: UUID
    project_name: str
    count: int
    tasks: list[DashboardBreakdownTask]
    has_more: bool


class DashboardBreakdown(BaseModel):
    metric: DashboardMetric
    total_count: int
    projects: list[DashboardProjectBreakdown]
