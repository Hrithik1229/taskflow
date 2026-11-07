from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User
from app.schemas.notification import NotificationListResponse, NotificationRead
from app.security.dependencies import get_current_user
from app.services.notifications import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UserDependency = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=NotificationListResponse)
async def list_my_notifications(
    session: SessionDependency,
    user: UserDependency,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationListResponse:
    return await list_notifications(
        session,
        user_id=user.id,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def read_notification(
    notification_id: UUID,
    session: SessionDependency,
    user: UserDependency,
) -> NotificationRead:
    return await mark_notification_read(
        session,
        notification_id=notification_id,
        user_id=user.id,
    )


@router.patch("/read-all", response_model=dict)
async def read_all_notifications(
    session: SessionDependency,
    user: UserDependency,
) -> dict:
    return await mark_all_notifications_read(session, user_id=user.id)
