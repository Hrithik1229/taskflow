from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User
from app.schemas.notification import NotificationListResponse, NotificationRead


async def _notification_read(
    session: AsyncSession, notification: Notification
) -> NotificationRead:
    actor = None
    if notification.actor_id is not None:
        actor = await session.get(User, notification.actor_id)
    return NotificationRead(
        id=notification.id,
        type=notification.type,
        payload=notification.payload,
        actor=actor,
        project_id=notification.project_id,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


async def list_notifications(
    session: AsyncSession,
    *,
    user_id: UUID,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> NotificationListResponse:
    base_filter = [Notification.recipient_id == user_id]
    if unread_only:
        base_filter.append(Notification.read_at.is_(None))

    total = (
        await session.scalar(select(func.count(Notification.id)).where(*base_filter))
    ) or 0

    unread_count = (
        await session.scalar(
            select(func.count(Notification.id)).where(
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
        )
    ) or 0

    notifications = (
        await session.scalars(
            select(Notification)
            .where(*base_filter)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [await _notification_read(session, n) for n in notifications]
    return NotificationListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


async def mark_notification_read(
    session: AsyncSession,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> NotificationRead:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.recipient_id != user_id:
        raise HTTPException(status_code=404, detail="Notification not found.")

    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return await _notification_read(session, notification)


async def mark_all_notifications_read(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> dict[str, int]:
    now = datetime.now(UTC)
    result = await session.execute(
        update(Notification)
        .where(
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
        .returning(Notification.id)
    )
    updated = len(result.all())
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return {"marked_read": updated}
