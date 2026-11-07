from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User
from app.schemas.activity import ActivityListResponse
from app.security.dependencies import get_current_user
from app.services.activity import list_project_activity, list_recent_activity

router = APIRouter(tags=["activity"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UserDependency = Annotated[User, Depends(get_current_user)]


@router.get(
    "/api/projects/{project_id}/activity",
    response_model=ActivityListResponse,
)
async def project_activity(
    project_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActivityListResponse:
    return await list_project_activity(
        session,
        project_id=project_id,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/api/activity/recent",
    response_model=ActivityListResponse,
)
async def recent_activity(
    session: SessionDependency,
    user: UserDependency,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ActivityListResponse:
    """Return up to `limit` recent activity entries across all the caller's projects."""
    return await list_recent_activity(session, user_id=user.id, limit=limit)
