from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityLog, Project, ProjectMember, User
from app.schemas.activity import ActivityActor, ActivityListResponse, ActivityRead
from app.security.permissions import get_membership


async def _load_activity(session: AsyncSession, log: ActivityLog) -> ActivityRead:
    actor = await session.get(User, log.actor_id)
    if actor is None:
        # Fallback for deleted users
        actor_summary = ActivityActor(id=log.actor_id, username="[deleted]")
    else:
        actor_summary = ActivityActor(id=actor.id, username=actor.username)
    project = await session.get(Project, log.project_id)
    project_name = project.name if project else None
    return ActivityRead(
        id=log.id,
        project_id=log.project_id,
        project_name=project_name,
        actor=actor_summary,
        action=log.action,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        details=log.details,
        created_at=log.created_at,
    )


async def list_project_activity(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> ActivityListResponse:
    membership = await get_membership(session, project_id, user_id)
    if membership is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    total = (
        await session.scalar(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.project_id == project_id
            )
        )
    ) or 0

    logs = (
        await session.scalars(
            select(ActivityLog)
            .where(ActivityLog.project_id == project_id)
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    items = [await _load_activity(session, log) for log in logs]
    return ActivityListResponse(items=items, total=total, limit=limit, offset=offset)


async def list_recent_activity(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int = 20,
) -> ActivityListResponse:
    """Return recent activity across all projects the caller is a member of."""
    # Subquery: project IDs where caller is a member
    member_project_ids = (
        await session.scalars(
            select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        )
    ).all()

    if not member_project_ids:
        return ActivityListResponse(items=[], total=0, limit=limit, offset=0)

    logs = (
        await session.scalars(
            select(ActivityLog)
            .where(ActivityLog.project_id.in_(member_project_ids))
            .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
            .limit(limit)
        )
    ).all()

    items = [await _load_activity(session, log) for log in logs]
    return ActivityListResponse(items=items, total=len(items), limit=limit, offset=0)
