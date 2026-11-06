from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.common.errors import TaskVersionConflict
from app.common.outbox import OutboxEvent
from app.common.task_lock import lock_project_tasks
from app.models import (
    ActivityLog,
    Notification,
    Project,
    ProjectMember,
    Task,
    TaskPriority,
    TaskStatus,
    User,
)
from app.schemas.task import (
    DashboardBreakdown,
    DashboardBreakdownTask,
    DashboardMetric,
    DashboardProjectBreakdown,
    DashboardSummary,
    TaskCreate,
    TaskListResponse,
    TaskMove,
    TaskMoveResponse,
    TaskPosition,
    TaskRead,
    TaskUpdate,
    TaskUserSummary,
)
from app.security.permissions import ProjectAction, can_perform, get_membership

BOARD_TASK_LIMIT = 500
DEFAULT_TASK_LIMIT = 100
_MUTABLE_FIELDS = {"title", "description", "priority", "assigned_to", "due_at"}


async def _load_task(session: AsyncSession, task_id: UUID) -> TaskRead | None:
    assignee = aliased(User)
    creator = aliased(User)
    reviewer = aliased(User)
    submitter = aliased(User)
    status_actor = aliased(User)
    completer = aliased(User)
    row = (
        await session.execute(
            select(
                Task,
                assignee,
                creator,
                reviewer,
                submitter,
                status_actor,
                completer,
                select(ActivityLog.id)
                .where(
                    ActivityLog.entity_id == Task.id,
                    ActivityLog.action == "task.completion_credit_removed",
                )
                .exists(),
            )
            .outerjoin(assignee, assignee.id == Task.assigned_to)
            .join(creator, creator.id == Task.created_by)
            .outerjoin(reviewer, reviewer.id == Task.reviewer_id)
            .outerjoin(submitter, submitter.id == Task.review_requested_by)
            .outerjoin(status_actor, status_actor.id == Task.status_changed_by)
            .outerjoin(completer, completer.id == Task.completed_by)
            .where(Task.id == task_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        return None
    (
        task,
        assigned_user,
        created_user,
        reviewer_user,
        submitter_user,
        status_actor_user,
        completer_user,
        completed_by_removed,
    ) = row

    def summary(user: User | None) -> TaskUserSummary | None:
        if user is None:
            return None
        return TaskUserSummary(id=user.id, username=user.username)

    return TaskRead(
        id=task.id,
        project_id=task.project_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        assigned_to=task.assigned_to,
        assignee=summary(assigned_user),
        reviewer_id=task.reviewer_id,
        reviewer=summary(reviewer_user),
        review_requested_by=summary(submitter_user),
        status_changed_by=summary(status_actor_user),
        status_changed_at=task.status_changed_at,
        completed_by=summary(completer_user),
        completed_at=task.completed_at,
        completed_by_removed=completed_by_removed,
        created_by=task.created_by,
        creator=TaskUserSummary(
            id=created_user.id,
            username=created_user.username,
        ),
        due_at=task.due_at,
        position=task.position,
        version=task.version,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _require_action(
    membership: ProjectMember,
    action: ProjectAction,
    *,
    user_id: UUID,
    task: Task | None = None,
    reviewer_id: UUID | None = None,
    review_requested_by_id: UUID | None = None,
) -> None:
    if not can_perform(
        membership.role,
        action,
        user_id=user_id,
        resource_owner_id=task.created_by if task is not None else None,
        assignee_id=task.assigned_to if task is not None else None,
        reviewer_id=reviewer_id
        if reviewer_id is not None
        else task.reviewer_id
        if task is not None
        else None,
        review_requested_by_id=review_requested_by_id
        if review_requested_by_id is not None
        else task.review_requested_by
        if task is not None
        else None,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )


async def _require_project_membership(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> ProjectMember:
    membership = await get_membership(session, project_id, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return membership


async def _validate_assignee(
    session: AsyncSession,
    project_id: UUID,
    assignee_id: UUID | None,
) -> None:
    if assignee_id is None:
        return
    membership = await get_membership(session, project_id, assignee_id)
    if membership is None:
        raise HTTPException(
            status_code=422,
            detail="Assignee must be a current project member.",
        )


async def _validate_reviewer(
    session: AsyncSession,
    project_id: UUID,
    reviewer_id: UUID | None,
    *,
    submitter_id: UUID,
) -> None:
    if reviewer_id is None:
        return
    if reviewer_id == submitter_id:
        raise HTTPException(
            status_code=422,
            detail="The person submitting the task cannot review it.",
        )
    if await get_membership(session, project_id, reviewer_id) is None:
        raise HTTPException(
            status_code=422,
            detail="Reviewer must be a current project member.",
        )


def _outbox(
    *,
    project_id: UUID,
    task_id: UUID,
    action: str,
    client_mutation_id: str | None,
    **details: object,
) -> OutboxEvent:
    payload: dict[str, object] = {
        "action": action,
        "task_id": str(task_id),
        **details,
    }
    if client_mutation_id is not None:
        payload["client_mutation_id"] = client_mutation_id
    return OutboxEvent(
        event="task_changed",
        project_id=project_id,
        payload=payload,
    )


def _notification_event(
    notification: Notification,
    *,
    client_mutation_id: str | None,
) -> OutboxEvent:
    return OutboxEvent(
        event="notification_created",
        project_id=notification.project_id,
        payload={
            "recipient_id": str(notification.recipient_id),
            "client_mutation_id": client_mutation_id,
            "notification": {
                "id": str(notification.id),
                "type": notification.type,
                "created_at": (
                    notification.created_at.isoformat()
                    if notification.created_at
                    else None
                ),
                "payload": notification.payload,
            },
        },
    )


async def create_task(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_id: UUID,
    request: TaskCreate,
    client_mutation_id: str | None = None,
) -> tuple[TaskRead, list[OutboxEvent]]:
    membership = await _require_project_membership(session, project_id, actor_id)
    _require_action(membership, ProjectAction.TASK_CREATE, user_id=actor_id)
    await lock_project_tasks(session, project_id)
    try:
        membership = await _require_project_membership(session, project_id, actor_id)
        _require_action(membership, ProjectAction.TASK_CREATE, user_id=actor_id)
    except HTTPException:
        await session.rollback()
        raise
    try:
        await _validate_assignee(session, project_id, request.assigned_to)
    except HTTPException:
        await session.rollback()
        raise

    max_position = await session.scalar(
        select(func.max(Task.position)).where(
            Task.project_id == project_id,
            Task.status == request.status,
        )
    )
    task_id = uuid4()
    task = Task(
        id=task_id,
        project_id=project_id,
        title=request.title,
        description=request.description,
        status=request.status,
        priority=request.priority,
        assigned_to=request.assigned_to,
        created_by=actor_id,
        due_at=request.due_at,
        position=(max_position if max_position is not None else -1) + 1,
        version=1,
    )
    session.add(task)
    session.add(
        ActivityLog(
            project_id=project_id,
            actor_id=actor_id,
            action="task.created",
            entity_type="task",
            entity_id=task_id,
            details={
                "status": task.status.value,
                "priority": task.priority.value,
            },
        )
    )
    if task.assigned_to is not None and task.assigned_to != actor_id:
        notification_id = uuid4()
        notification = Notification(
            id=notification_id,
            recipient_id=task.assigned_to,
            project_id=project_id,
            actor_id=actor_id,
            type="task_assigned",
            payload={"task_id": str(task_id), "title": task.title},
        )
        session.add(notification)
    else:
        notification = None
    try:
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    result = await _load_task(session, task_id)
    if result is None:
        raise RuntimeError("Created task could not be reloaded.")
    events = [
        _outbox(
            project_id=project_id,
            task_id=task_id,
            action="task.created",
            client_mutation_id=client_mutation_id,
            task=result.model_dump(mode="json"),
        )
    ]
    if notification is not None:
        events.append(
            OutboxEvent(
                event="notification_created",
                project_id=project_id,
                payload={
                    "recipient_id": str(notification.recipient_id),
                    "client_mutation_id": client_mutation_id,
                    "notification": {
                        "id": str(notification.id),
                        "type": notification.type,
                        "created_at": (
                            notification.created_at.isoformat()
                            if notification.created_at
                            else None
                        ),
                        "payload": notification.payload,
                    },
                },
            )
        )
    return result, events


async def get_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
) -> TaskRead:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    await _require_project_membership(session, task.project_id, user_id)
    result = await _load_task(session, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return result


async def list_tasks(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    status_filter: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    assigned_to: UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    overdue: bool = False,
    query: str | None = None,
    limit: int = DEFAULT_TASK_LIMIT,
    offset: int = 0,
    sort: str = "status",
    direction: str = "asc",
) -> TaskListResponse:
    await _require_project_membership(session, project_id, user_id)
    filters = [Task.project_id == project_id]
    if status_filter is not None:
        filters.append(Task.status == status_filter)
    if priority is not None:
        filters.append(Task.priority == priority)
    if assigned_to is not None:
        filters.append(Task.assigned_to == assigned_to)
    if due_before is not None:
        filters.append(Task.due_at <= due_before)
    if due_after is not None:
        filters.append(Task.due_at >= due_after)
    if overdue:
        filters.extend(
            [
                Task.due_at < datetime.now(UTC),
                Task.status != TaskStatus.COMPLETED,
            ]
        )
    if query:
        escaped_query = (
            query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped_query}%"
        filters.append(
            or_(
                Task.title.ilike(pattern, escape="\\"),
                Task.description.ilike(pattern, escape="\\"),
            )
        )

    total = await session.scalar(select(func.count(Task.id)).where(*filters)) or 0
    if sort == "status":
        order_by = [Task.status.asc(), Task.position.asc(), Task.id.asc()]
    else:
        sort_column = getattr(Task, sort)
        primary_order = sort_column.desc() if direction == "desc" else sort_column.asc()
        order_by = [primary_order, Task.id.asc()]
        if sort == "position":
            order_by.insert(0, Task.status.asc())

    task_ids = (
        await session.scalars(
            select(Task.id)
            .where(*filters)
            .order_by(*order_by)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items: list[TaskRead] = []
    for task_id in task_ids:
        result = await _load_task(session, task_id)
        if result is not None:
            items.append(result)
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)


async def update_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    request: TaskUpdate,
    client_mutation_id: str | None = None,
) -> tuple[TaskRead, list[OutboxEvent]]:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    membership = await _require_project_membership(session, task.project_id, user_id)
    await lock_project_tasks(session, task.project_id)
    task = await session.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        membership = await _require_project_membership(
            session, task.project_id, user_id
        )
        requested_fields = request.model_fields_set - {"expected_version"}
        reviewer_field_requested = "reviewer_id" in requested_fields
        editable_fields = requested_fields - {"reviewer_id"}
        if editable_fields:
            _require_action(
                membership,
                ProjectAction.TASK_EDIT,
                user_id=user_id,
                task=task,
            )
        if reviewer_field_requested:
            if task.status != TaskStatus.REVIEW:
                raise HTTPException(
                    status_code=422,
                    detail="A reviewer can only be set while the task is in Review.",
                )
            if not can_perform(
                membership.role,
                ProjectAction.TASK_SET_REVIEWER,
                user_id=user_id,
                reviewer_id=task.reviewer_id,
                review_requested_by_id=task.review_requested_by,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to change this reviewer.",
                )
        await _validate_assignee(
            session,
            task.project_id,
            request.assigned_to if "assigned_to" in request.model_fields_set else None,
        )
        if reviewer_field_requested:
            await _validate_reviewer(
                session,
                task.project_id,
                request.reviewer_id,
                submitter_id=task.review_requested_by or task.created_by,
            )
    except HTTPException:
        await session.rollback()
        raise
    if task.version != request.expected_version:
        current = await _load_task(session, task_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        await session.rollback()
        raise TaskVersionConflict(current)

    changes = request.model_dump(
        exclude_unset=True,
        exclude={"expected_version"},
    )
    changed = {
        field: value
        for field, value in changes.items()
        if getattr(task, field) != value
    }
    old_values = {field: getattr(task, field) for field in changed}
    values = {**changed, "version": Task.version + 1, "updated_at": func.now()}
    updated_id = await session.scalar(
        update(Task)
        .where(Task.id == task_id, Task.version == request.expected_version)
        .values(**values)
        .returning(Task.id)
    )
    if updated_id is None:
        current = await _load_task(session, task_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        await session.rollback()
        raise TaskVersionConflict(current)

    session.add(
        ActivityLog(
            project_id=task.project_id,
            actor_id=user_id,
            action="task.updated",
            entity_type="task",
            entity_id=task_id,
            details={
                field: {
                    "old": (
                        str(old_values[field])
                        if old_values[field] is not None
                        else None
                    ),
                    "new": (
                        str(changed[field]) if changed[field] is not None else None
                    ),
                }
                for field in changed
                if field != "description"
            },
        )
    )
    new_assignee = changed.get("assigned_to")
    notifications: list[Notification] = []
    if (
        "assigned_to" in changed
        and new_assignee is not None
        and new_assignee != user_id
    ):
        notification = Notification(
            id=uuid4(),
            recipient_id=new_assignee,
            project_id=task.project_id,
            actor_id=user_id,
            type="task_assigned",
            payload={
                "task_id": str(task_id),
                "title": changed.get("title", task.title),
            },
        )
        session.add(notification)
        notifications.append(notification)
    new_reviewer_id = changed.get("reviewer_id")
    if (
        "reviewer_id" in changed
        and new_reviewer_id is not None
        and new_reviewer_id != user_id
    ):
        notification = Notification(
            id=uuid4(),
            recipient_id=new_reviewer_id,
            project_id=task.project_id,
            actor_id=user_id,
            type="review_requested",
            payload={
                "task_id": str(task_id),
                "title": changed.get("title", task.title),
            },
        )
        session.add(notification)
        notifications.append(notification)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    result = await _load_task(session, task_id)
    if result is None:
        raise RuntimeError("Updated task could not be reloaded.")
    events = [
        _outbox(
            project_id=task.project_id,
            task_id=task_id,
            action="task.updated",
            client_mutation_id=client_mutation_id,
            version=result.version,
            task=result.model_dump(mode="json"),
        )
    ]
    events.extend(
        _notification_event(
            notification,
            client_mutation_id=client_mutation_id,
        )
        for notification in notifications
    )
    return result, events


async def move_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    request: TaskMove,
    client_mutation_id: str | None = None,
) -> tuple[TaskMoveResponse, list[OutboxEvent]]:
    initial = await session.get(Task, task_id)
    if initial is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    membership = await _require_project_membership(session, initial.project_id, user_id)
    _require_action(membership, ProjectAction.TASK_MOVE, user_id=user_id)
    await lock_project_tasks(session, initial.project_id)
    try:
        membership = await _require_project_membership(
            session, initial.project_id, user_id
        )
        _require_action(membership, ProjectAction.TASK_MOVE, user_id=user_id)
    except HTTPException:
        await session.rollback()
        raise
    tasks = list(
        (
            await session.scalars(
                select(Task)
                .where(Task.project_id == initial.project_id)
                .order_by(Task.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
    )
    task = next((item for item in tasks if item.id == task_id), None)
    if task is None:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.version != request.expected_version:
        current = await _load_task(session, task_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Task not found.")
        await session.rollback()
        raise TaskVersionConflict(current)

    source_status = task.status
    status_changed = source_status != request.status
    if source_status == TaskStatus.REVIEW and request.status == TaskStatus.TODO:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail="Tasks in Review can only move to In progress or Completed.",
        )
    if source_status == TaskStatus.REVIEW and status_changed:
        if not can_perform(
            membership.role,
            ProjectAction.TASK_REVIEW_DECIDE,
            user_id=user_id,
            reviewer_id=task.reviewer_id,
        ):
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only the reviewer, project owner, or admin can decide "
                    "a task in Review."
                ),
            )
    if request.status == TaskStatus.REVIEW and status_changed:
        if request.reviewer_id is None:
            await session.rollback()
            raise HTTPException(
                status_code=422,
                detail="Choose a reviewer when moving a task into Review.",
            )
        try:
            await _validate_reviewer(
                session,
                task.project_id,
                request.reviewer_id,
                submitter_id=user_id,
            )
        except HTTPException:
            await session.rollback()
            raise
    elif request.reviewer_id is not None:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail="reviewer_id is only accepted when moving a task into Review.",
        )

    source_tasks = sorted(
        (item for item in tasks if item.status == source_status),
        key=lambda item: (item.position, item.id),
    )
    destination_tasks = (
        source_tasks
        if request.status == source_status
        else sorted(
            (item for item in tasks if item.status == request.status),
            key=lambda item: (item.position, item.id),
        )
    )
    source_remaining = [item for item in source_tasks if item.id != task.id]
    destination_base = (
        source_remaining if request.status == source_status else destination_tasks
    )
    insertion_index = min(request.position, len(destination_base))
    destination_final = list(destination_base)
    destination_final.insert(insertion_index, task)
    columns = (
        [(request.status, destination_final)]
        if source_status == request.status
        else [(source_status, source_remaining), (request.status, destination_final)]
    )

    changed_positions: list[TaskPosition] = []
    now = datetime.now(UTC)
    task_values: dict[str, object] = {}
    if status_changed:
        task_values.update(status_changed_by=user_id, status_changed_at=now)
    if request.status == TaskStatus.REVIEW and status_changed:
        task_values.update(
            reviewer_id=request.reviewer_id,
            review_requested_by=user_id,
        )
    elif (
        source_status == TaskStatus.REVIEW and request.status == TaskStatus.IN_PROGRESS
    ):
        task_values.update(reviewer_id=None, review_requested_by=None)
    if request.status == TaskStatus.COMPLETED and status_changed:
        task_values.update(
            completed_by=(
                task.review_requested_by
                if source_status == TaskStatus.REVIEW
                else user_id
            ),
            completed_at=now,
        )
    elif source_status == TaskStatus.COMPLETED and status_changed:
        task_values.update(completed_by=None, completed_at=None)

    actor = await session.get(User, user_id)
    if actor is None:
        await session.rollback()
        raise HTTPException(status_code=404, detail="User not found.")
    reviewer_id = (
        request.reviewer_id
        if request.status == TaskStatus.REVIEW and status_changed
        else task.reviewer_id
    )
    reviewer = await session.get(User, reviewer_id) if reviewer_id is not None else None
    submitter_id = (
        user_id
        if request.status == TaskStatus.REVIEW and status_changed
        else task.review_requested_by
    )
    submitter = (
        await session.get(User, submitter_id) if submitter_id is not None else None
    )
    credited_id = (
        task_values.get("completed_by")
        if request.status == TaskStatus.COMPLETED and status_changed
        else task.completed_by
    )
    credited_user = (
        await session.get(User, credited_id) if credited_id is not None else None
    )

    def summary(user: User | None) -> dict[str, str] | None:
        if user is None:
            return None
        return {"id": str(user.id), "username": user.username}

    notifications: list[Notification] = []
    if (
        request.status == TaskStatus.REVIEW
        and status_changed
        and reviewer is not None
        and reviewer.id != user_id
    ):
        notification = Notification(
            id=uuid4(),
            recipient_id=reviewer.id,
            project_id=task.project_id,
            actor_id=user_id,
            type="review_requested",
            payload={"task_id": str(task_id), "title": task.title},
        )
        session.add(notification)
        notifications.append(notification)
    if (
        source_status == TaskStatus.REVIEW
        and request.status in {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED}
        and submitter is not None
        and submitter.id != user_id
    ):
        notification = Notification(
            id=uuid4(),
            recipient_id=submitter.id,
            project_id=task.project_id,
            actor_id=user_id,
            type=(
                "changes_requested"
                if request.status == TaskStatus.IN_PROGRESS
                else "review_completed"
            ),
            payload={"task_id": str(task_id), "title": task.title},
        )
        session.add(notification)
        notifications.append(notification)

    try:
        for column_status, column_tasks in columns:
            for position, item in enumerate(column_tasks):
                position_changed = (
                    item.position != position or item.status != column_status
                )
                is_moved = item.id == task.id
                if not position_changed and not is_moved:
                    continue
                next_version = item.version + 1
                await session.execute(
                    update(Task)
                    .where(Task.id == item.id)
                    .values(
                        status=column_status,
                        position=position,
                        version=Task.version + 1,
                        updated_at=func.now(),
                        **(task_values if is_moved else {}),
                    )
                )
                if not is_moved:
                    changed_positions.append(
                        TaskPosition(
                            id=item.id,
                            position=position,
                            version=next_version,
                        )
                    )
        session.add(
            ActivityLog(
                project_id=task.project_id,
                actor_id=user_id,
                action="task.moved",
                entity_type="task",
                entity_id=task_id,
                details={
                    "from_status": source_status.value,
                    "to_status": request.status.value,
                    "position": insertion_index,
                    "mover": summary(actor),
                    "reviewer": summary(reviewer),
                    "review_requested_by": summary(submitter),
                    "credited_completer": summary(credited_user),
                },
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    moved = await _load_task(session, task_id)
    if moved is None:
        raise RuntimeError("Moved task could not be reloaded.")
    events = [
        _outbox(
            project_id=task.project_id,
            task_id=task_id,
            action="task.moved",
            client_mutation_id=client_mutation_id,
            version=moved.version,
            task=moved.model_dump(mode="json"),
            affected=[sibling.model_dump(mode="json") for sibling in changed_positions],
        )
    ]
    events.extend(
        _notification_event(
            notification,
            client_mutation_id=client_mutation_id,
        )
        for notification in notifications
    )
    return TaskMoveResponse(task=moved, affected=changed_positions), events


async def delete_task(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    client_mutation_id: str | None = None,
) -> list[OutboxEvent]:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    membership = await _require_project_membership(session, task.project_id, user_id)
    await lock_project_tasks(session, task.project_id)
    task = await session.scalar(
        select(Task)
        .where(Task.id == task_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if task is None:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Task not found.")
    try:
        membership = await _require_project_membership(
            session, task.project_id, user_id
        )
        _require_action(
            membership, ProjectAction.TASK_DELETE, user_id=user_id, task=task
        )
    except HTTPException:
        await session.rollback()
        raise
    project_id = task.project_id
    task_status = task.status
    removed_position = task.position
    deleted_task = {
        "id": str(task.id),
        "project_id": str(task.project_id),
        "title": task.title,
        "status": task.status.value,
        "position": task.position,
        "version": task.version + 1,
    }
    try:
        session.add(
            ActivityLog(
                project_id=project_id,
                actor_id=user_id,
                action="task.deleted",
                entity_type="task",
                entity_id=task_id,
                details={"title": task.title},
            )
        )
        await session.delete(task)
        siblings = list(
            (
                await session.scalars(
                    select(Task)
                    .where(
                        Task.project_id == project_id,
                        Task.status == task_status,
                        Task.position > removed_position,
                    )
                    .order_by(Task.id)
                    .with_for_update()
                )
            ).all()
        )
        affected = [
            {
                "id": str(sibling.id),
                "position": sibling.position - 1,
                "version": sibling.version + 1,
            }
            for sibling in siblings
        ]
        for sibling in siblings:
            await session.execute(
                update(Task)
                .where(Task.id == sibling.id)
                .values(
                    position=Task.position - 1,
                    version=Task.version + 1,
                    updated_at=func.now(),
                )
            )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return [
        _outbox(
            project_id=project_id,
            task_id=task_id,
            action="task.deleted",
            client_mutation_id=client_mutation_id,
            version=deleted_task["version"],
            task=deleted_task,
            affected=affected,
        )
    ]


async def dashboard_summary(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> DashboardSummary:
    filters = _dashboard_metric_filters(user_id, datetime.now(UTC))
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(case((filters["total"], 1), else_=0)), 0),
                func.coalesce(
                    func.sum(case((filters["assigned_to_me"], 1), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((filters["overdue"], 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(case((filters["completed"], 1), else_=0)),
                    0,
                ),
            )
            .join(ProjectMember, ProjectMember.project_id == Task.project_id)
            .where(ProjectMember.user_id == user_id)
        )
    ).one()
    return DashboardSummary(
        total_tasks=row[0],
        assigned_to_me=row[1],
        overdue=row[2],
        completed=row[3],
    )


def _dashboard_metric_filters(
    user_id: UUID,
    now: datetime,
) -> dict[DashboardMetric, ColumnElement[bool]]:
    return {
        "total": true(),
        "overdue": (Task.due_at < now) & (Task.status != TaskStatus.COMPLETED),
        "completed": Task.status == TaskStatus.COMPLETED,
        "assigned_to_me": Task.assigned_to == user_id,
    }


async def dashboard_breakdown(
    session: AsyncSession,
    *,
    user_id: UUID,
    metric: DashboardMetric,
) -> DashboardBreakdown:
    metric_filter = _dashboard_metric_filters(user_id, datetime.now(UTC))[metric]
    count_column = func.count(Task.id)
    project_rows = (
        await session.execute(
            select(Project.id, Project.name, count_column)
            .join(Task, Task.project_id == Project.id)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user_id, metric_filter)
            .group_by(Project.id, Project.name)
            .having(count_column > 0)
            .order_by(count_column.desc(), Project.name.asc())
        )
    ).all()
    if not project_rows:
        return DashboardBreakdown(metric=metric, total_count=0, projects=[])

    ranked_tasks = (
        select(
            Task.id.label("id"),
            Task.project_id.label("project_id"),
            Task.title.label("title"),
            Task.status.label("status"),
            Task.priority.label("priority"),
            Task.due_at.label("due_at"),
            Task.assigned_to.label("assigned_to"),
            Task.completed_by.label("completed_by"),
            select(ActivityLog.id)
            .where(
                ActivityLog.entity_id == Task.id,
                ActivityLog.action == "task.completion_credit_removed",
            )
            .exists()
            .label("completed_by_removed"),
            func.row_number()
            .over(
                partition_by=Task.project_id,
                order_by=(Task.title.asc(), Task.id.asc()),
            )
            .label("task_rank"),
        )
        .join(ProjectMember, ProjectMember.project_id == Task.project_id)
        .where(
            ProjectMember.user_id == user_id,
            Task.project_id.in_([row.id for row in project_rows]),
            metric_filter,
        )
        .subquery()
    )
    assignee = aliased(User)
    completer = aliased(User)
    task_rows = (
        await session.execute(
            select(
                ranked_tasks.c.id,
                ranked_tasks.c.project_id,
                ranked_tasks.c.title,
                ranked_tasks.c.status,
                ranked_tasks.c.priority,
                ranked_tasks.c.due_at,
                ranked_tasks.c.completed_by_removed,
                assignee,
                completer,
            )
            .outerjoin(assignee, assignee.id == ranked_tasks.c.assigned_to)
            .outerjoin(completer, completer.id == ranked_tasks.c.completed_by)
            .where(ranked_tasks.c.task_rank <= 20)
            .order_by(ranked_tasks.c.project_id, ranked_tasks.c.task_rank)
        )
    ).all()

    tasks_by_project: dict[UUID, list[DashboardBreakdownTask]] = {
        row.id: [] for row in project_rows
    }
    for (
        task_id,
        project_id,
        title,
        task_status,
        priority,
        due_at,
        completed_by_removed,
        assigned_user,
        completed_user,
    ) in task_rows:
        tasks_by_project[project_id].append(
            DashboardBreakdownTask(
                id=task_id,
                title=title,
                status=task_status,
                priority=priority,
                due_at=due_at,
                assignee=(
                    TaskUserSummary(
                        id=assigned_user.id,
                        username=assigned_user.username,
                    )
                    if assigned_user is not None
                    else None
                ),
                completed_by=(
                    TaskUserSummary(
                        id=completed_user.id,
                        username=completed_user.username,
                    )
                    if task_status == TaskStatus.COMPLETED
                    and completed_user is not None
                    else None
                ),
                completed_by_removed=completed_by_removed,
            )
        )

    projects = [
        DashboardProjectBreakdown(
            project_id=project_id,
            project_name=project_name,
            count=count,
            tasks=tasks_by_project[project_id],
            has_more=count > 20,
        )
        for project_id, project_name, count in project_rows
    ]
    return DashboardBreakdown(
        metric=metric,
        total_count=sum(project.count for project in projects),
        projects=projects,
    )
