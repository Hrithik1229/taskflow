from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ProjectMember, TaskPriority, TaskStatus, User
from app.schemas.task import (
    DashboardBreakdown,
    DashboardMetric,
    DashboardSummary,
    SortDirection,
    SortField,
    TaskCreate,
    TaskListResponse,
    TaskMove,
    TaskMoveResponse,
    TaskRead,
    TaskUpdate,
)
from app.security.dependencies import get_current_user
from app.security.permissions import require_project_member
from app.services.tasks import (
    BOARD_TASK_LIMIT,
    create_task,
    dashboard_breakdown,
    dashboard_summary,
    delete_task,
    get_task,
    list_tasks,
    move_task,
    update_task,
)
from app.sockets.emitters import publish_outbox_after_commit

router = APIRouter(tags=["tasks"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UserDependency = Annotated[User, Depends(get_current_user)]
MutationId = Annotated[
    str | None,
    Header(alias="X-Client-Mutation-Id", max_length=128),
]


def _require_aware_filter(value: datetime | None, name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise HTTPException(
            status_code=422,
            detail=f"{name} must include a timezone.",
        )


@router.post(
    "/api/projects/{project_id}/tasks",
    response_model=TaskRead,
    status_code=201,
)
async def create(
    project_id: UUID,
    payload: TaskCreate,
    session: SessionDependency,
    user: UserDependency,
    _membership: Annotated[ProjectMember, Depends(require_project_member)],
    mutation_id: MutationId = None,
) -> TaskRead:
    task, outbox = await create_task(
        session,
        project_id=project_id,
        actor_id=user.id,
        request=payload,
        client_mutation_id=mutation_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return task


@router.get(
    "/api/projects/{project_id}/tasks",
    response_model=TaskListResponse,
)
async def list_project_tasks(
    project_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    _membership: Annotated[ProjectMember, Depends(require_project_member)],
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assigned_to: UUID | None = None,
    priority: TaskPriority | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    overdue: bool = False,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=BOARD_TASK_LIMIT)] = BOARD_TASK_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: SortField = "status",
    direction: SortDirection = "asc",
) -> TaskListResponse:
    _require_aware_filter(due_before, "due_before")
    _require_aware_filter(due_after, "due_after")
    return await list_tasks(
        session,
        project_id=project_id,
        user_id=user.id,
        status_filter=status_filter,
        priority=priority,
        assigned_to=assigned_to,
        due_before=due_before,
        due_after=due_after,
        overdue=overdue,
        query=q,
        limit=limit,
        offset=offset,
        sort=sort,
        direction=direction,
    )


@router.get("/api/tasks/{task_id}", response_model=TaskRead)
async def read_task(
    task_id: UUID,
    session: SessionDependency,
    user: UserDependency,
) -> TaskRead:
    return await get_task(session, task_id=task_id, user_id=user.id)


@router.patch("/api/tasks/{task_id}", response_model=TaskRead)
async def update(
    task_id: UUID,
    payload: TaskUpdate,
    session: SessionDependency,
    user: UserDependency,
    mutation_id: MutationId = None,
) -> TaskRead:
    task, outbox = await update_task(
        session,
        task_id=task_id,
        user_id=user.id,
        request=payload,
        client_mutation_id=mutation_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return task


@router.patch("/api/tasks/{task_id}/move", response_model=TaskMoveResponse)
async def move(
    task_id: UUID,
    payload: TaskMove,
    session: SessionDependency,
    user: UserDependency,
    mutation_id: MutationId = None,
) -> TaskMoveResponse:
    result, outbox = await move_task(
        session,
        task_id=task_id,
        user_id=user.id,
        request=payload,
        client_mutation_id=mutation_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return result


@router.delete("/api/tasks/{task_id}", status_code=204)
async def delete(
    task_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    mutation_id: MutationId = None,
) -> Response:
    outbox = await delete_task(
        session,
        task_id=task_id,
        user_id=user.id,
        client_mutation_id=mutation_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return Response(status_code=204)


dashboard_router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@dashboard_router.get("/summary", response_model=DashboardSummary)
async def summary(
    session: SessionDependency,
    user: UserDependency,
) -> DashboardSummary:
    return await dashboard_summary(session, user_id=user.id)


@dashboard_router.get("/summary/breakdown", response_model=DashboardBreakdown)
async def summary_breakdown(
    session: SessionDependency,
    user: UserDependency,
    metric: DashboardMetric,
) -> DashboardBreakdown:
    return await dashboard_breakdown(
        session,
        user_id=user.id,
        metric=metric,
    )
