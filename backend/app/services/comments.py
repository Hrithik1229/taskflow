from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.outbox import OutboxEvent
from app.models import ActivityLog, Comment, Notification, Task, User
from app.schemas.comment import (
    CommentAuthor,
    CommentCreate,
    CommentListResponse,
    CommentRead,
)
from app.security.permissions import get_membership


async def _require_task_member(
    session: AsyncSession,
    task_id: UUID,
    user_id: UUID,
) -> tuple[Task, User]:
    """Return (task, user) if user is a member of the task's project; 404 otherwise."""
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    membership = await get_membership(session, task.project_id, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    actor = await session.get(User, user_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return task, actor


def _comment_read(comment: Comment, author: User) -> CommentRead:
    return CommentRead(
        id=comment.id,
        task_id=comment.task_id,
        content=comment.content,
        author=CommentAuthor(id=author.id, username=author.username),
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


async def create_comment(
    session: AsyncSession,
    *,
    task_id: UUID,
    actor_id: UUID,
    request: CommentCreate,
    client_mutation_id: str | None = None,
) -> tuple[CommentRead, list[OutboxEvent]]:
    task, actor = await _require_task_member(session, task_id, actor_id)
    project_id = task.project_id

    comment = Comment(
        id=uuid4(),
        task_id=task_id,
        user_id=actor_id,
        content=request.content,
        created_at=func.clock_timestamp(),
    )
    session.add(comment)

    # Activity log
    session.add(
        ActivityLog(
            project_id=project_id,
            actor_id=actor_id,
            action="comment.created",
            entity_type="task",
            entity_id=task_id,
            details={"task_title": task.title},
        )
    )

    # Notify task assignee and creator (if different from actor, deduplicated)
    notify_ids: set[UUID] = set()
    if task.assigned_to is not None and task.assigned_to != actor_id:
        notify_ids.add(task.assigned_to)
    if task.created_by != actor_id:
        notify_ids.add(task.created_by)

    notifications: list[Notification] = []
    for recipient_id in notify_ids:
        notification = Notification(
            id=uuid4(),
            recipient_id=recipient_id,
            project_id=project_id,
            actor_id=actor_id,
            type="comment_added",
            payload={"task_id": str(task_id), "task_title": task.title},
        )
        session.add(notification)
        notifications.append(notification)

    try:
        await session.flush()
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    # Reload comment to get server-defaulted created_at
    refreshed = await session.get(Comment, comment.id)
    if refreshed is None:
        raise RuntimeError("Comment could not be reloaded.")
    comment_read = _comment_read(refreshed, actor)

    events: list[OutboxEvent] = [
        OutboxEvent(
            event="comment_added",
            project_id=project_id,
            payload={
                "action": "comment.created",
                "task_id": str(task_id),
                "comment": comment_read.model_dump(mode="json"),
                "client_mutation_id": client_mutation_id,
            },
        )
    ]
    for notification in notifications:
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

    return comment_read, events


async def list_comments(
    session: AsyncSession,
    *,
    task_id: UUID,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> CommentListResponse:
    task, _actor = await _require_task_member(session, task_id, user_id)

    total = (
        await session.scalar(
            select(func.count(Comment.id)).where(Comment.task_id == task_id)
        )
    ) or 0

    rows = (
        await session.execute(
            select(Comment, User)
            .join(User, User.id == Comment.user_id)
            .where(Comment.task_id == task_id)
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [_comment_read(comment, user) for comment, user in rows]
    return CommentListResponse(items=items, total=total, limit=limit, offset=offset)
