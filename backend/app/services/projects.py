from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.outbox import OutboxEvent
from app.models import (
    ActivityLog,
    Project,
    ProjectMember,
    ProjectRole,
    Task,
    TaskStatus,
)
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.security.permissions import (
    ProjectAction,
    get_membership,
    require_action,
)


async def create_project_with_owner(
    session: AsyncSession,
    *,
    owner_id: UUID,
    name: str,
    description: str | None = None,
) -> Project:
    """Create a project, owner membership, and audit row without committing."""
    project = Project(
        id=uuid4(),
        name=name,
        description=description,
        owner_id=owner_id,
    )
    session.add(project)
    await session.flush()

    session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=owner_id,
            role=ProjectRole.OWNER,
        )
    )
    await session.flush()
    session.add(
        _activity(
            project_id=project.id,
            actor_id=owner_id,
            action="project.created",
            entity_type="project",
            entity_id=project.id,
            details={"name": project.name},
        )
    )
    await session.flush()
    return project


def _activity(
    *,
    project_id: UUID,
    actor_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    details: dict[str, object],
) -> ActivityLog:
    return ActivityLog(
        project_id=project_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )


async def _project_read(
    session: AsyncSession,
    project: Project,
    role: ProjectRole,
    *,
    include_task_counts: bool = False,
    user_id: UUID | None = None,
) -> ProjectRead:
    member_count = await session.scalar(
        select(func.count(ProjectMember.id)).where(
            ProjectMember.project_id == project.id
        )
    )
    task_counts = None
    overdue_task_count = None
    assigned_to_me_count = None
    if include_task_counts:
        counts = await session.execute(
            select(Task.status, func.count(Task.id))
            .where(Task.project_id == project.id)
            .group_by(Task.status)
        )
        task_counts = {task_status: 0 for task_status in TaskStatus}
        task_counts.update(dict(counts.all()))
        aggregates = (
            await session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    (Task.due_at < func.now())
                                    & (Task.status != TaskStatus.COMPLETED),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(case((Task.assigned_to == user_id, 1), else_=0)),
                        0,
                    ),
                ).where(Task.project_id == project.id)
            )
        ).one()
        overdue_task_count, assigned_to_me_count = aggregates
    return ProjectRead(
        id=project.id,
        name=project.name,
        description=project.description,
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        role=role,
        member_count=member_count or 0,
        task_counts=task_counts,
        overdue_task_count=overdue_task_count,
        assigned_to_me_count=assigned_to_me_count,
    )


async def create_project(
    session: AsyncSession,
    *,
    owner_id: UUID,
    request: ProjectCreate,
) -> tuple[ProjectRead, list[OutboxEvent]]:
    try:
        project = await create_project_with_owner(
            session,
            owner_id=owner_id,
            name=request.name,
            description=request.description,
        )
        await session.commit()
        await session.refresh(project)
    except Exception:
        await session.rollback()
        raise
    return (
        await _project_read(session, project, ProjectRole.OWNER),
        [
            OutboxEvent(
                event="project_changed",
                project_id=project.id,
                payload={
                    "action": "project.created",
                    "project_id": str(project.id),
                    "project": (
                        await _project_read(session, project, ProjectRole.OWNER)
                    ).model_dump(mode="json"),
                },
            )
        ],
    )


async def list_projects_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    offset: int = 0,
    limit: int = 20,
) -> list[ProjectRead]:
    memberships = (
        await session.scalars(
            select(ProjectMember)
            .where(ProjectMember.user_id == user_id)
            .order_by(ProjectMember.joined_at.desc(), ProjectMember.project_id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    projects: list[ProjectRead] = []
    for membership in memberships:
        project = await session.get(Project, membership.project_id)
        if project is not None:
            projects.append(await _project_read(session, project, membership.role))
    return projects


async def get_project(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
) -> ProjectRead:
    membership = await get_membership(session, project_id, user_id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return await _project_read(
        session,
        project,
        membership.role,
        include_task_counts=True,
        user_id=user_id,
    )


async def update_project(
    session: AsyncSession,
    *,
    membership: ProjectMember,
    actor_id: UUID,
    request: ProjectUpdate,
) -> tuple[ProjectRead, list[OutboxEvent]]:
    require_action(membership, ProjectAction.PROJECT_UPDATE, user_id=actor_id)
    project = await session.get(Project, membership.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    changes = request.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    session.add(
        _activity(
            project_id=project.id,
            actor_id=actor_id,
            action="project.updated",
            entity_type="project",
            entity_id=project.id,
            details={"changed_fields": sorted(changes)},
        )
    )
    try:
        await session.commit()
        await session.refresh(project)
    except Exception:
        await session.rollback()
        raise
    return (
        await _project_read(session, project, membership.role),
        [
            OutboxEvent(
                event="project_changed",
                project_id=project.id,
                payload={
                    "action": "project.updated",
                    "project_id": str(project.id),
                    "project": (
                        await _project_read(session, project, membership.role)
                    ).model_dump(mode="json"),
                },
            )
        ],
    )


async def delete_project(
    session: AsyncSession,
    *,
    membership: ProjectMember,
    actor_id: UUID,
) -> list[OutboxEvent]:
    require_action(membership, ProjectAction.PROJECT_DELETE, user_id=actor_id)
    project = await session.get(Project, membership.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    project_id = project.id
    deleted_project = {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "owner_id": str(project.owner_id),
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
    }
    try:
        await session.delete(project)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return [
        OutboxEvent(
            event="project_deleted",
            project_id=project_id,
            payload={
                "action": "project.deleted",
                "project": deleted_project,
            },
        )
    ]
