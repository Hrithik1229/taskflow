from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.outbox import OutboxEvent
from app.common.task_lock import lock_project_tasks
from app.models import ActivityLog, Notification, ProjectMember, ProjectRole, Task, User
from app.schemas.member import MemberAdd, MemberRead, MemberRoleUpdate
from app.security.permissions import ProjectAction, require_action
from app.services.tasks import _load_task


def _member_read(user: User, membership: ProjectMember) -> MemberRead:
    return MemberRead(
        id=user.id,
        username=user.username,
        email=user.email,
        role=membership.role,
        joined_at=membership.joined_at,
    )


async def list_project_members(
    session: AsyncSession, *, project_id: UUID
) -> list[MemberRead]:
    result = await session.execute(
        select(ProjectMember, User)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at, User.username)
    )
    return [_member_read(user, membership) for membership, user in result.all()]


async def add_member_by_email(
    session: AsyncSession,
    *,
    membership: ProjectMember,
    actor_id: UUID,
    request: MemberAdd,
) -> tuple[MemberRead, list[OutboxEvent]]:
    requested_role = ProjectRole(request.role)
    require_action(
        membership,
        ProjectAction.MEMBER_ADD,
        user_id=actor_id,
        target_role=requested_role,
    )
    if requested_role == ProjectRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A project cannot have another owner.",
        )

    user = await session.scalar(
        select(User).where(User.email == str(request.email).strip().lower())
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registered user with that email.",
        )
    existing = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == membership.project_id,
            ProjectMember.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This user is already a project member.",
        )

    new_membership = ProjectMember(
        project_id=membership.project_id,
        user_id=user.id,
        role=requested_role,
    )
    items_to_add: list[object] = [
        new_membership,
        ActivityLog(
            project_id=membership.project_id,
            actor_id=actor_id,
            action="member.added",
            entity_type="member",
            entity_id=user.id,
            details={"role": requested_role.value},
        ),
    ]
    notification = None
    if user.id != actor_id:
        notification = Notification(
            id=uuid4(),
            recipient_id=user.id,
            project_id=membership.project_id,
            actor_id=actor_id,
            type="member_added",
            payload={
                "project_id": str(membership.project_id),
                "role": requested_role.value,
            },
        )
        items_to_add.append(notification)
    session.add_all(items_to_add)
    try:
        await session.flush()
        await session.commit()
        await session.refresh(new_membership)
    except IntegrityError as exc:
        await session.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This user is already a project member.",
            ) from None
        raise
    except Exception:
        await session.rollback()
        raise

    events: list[OutboxEvent] = [
        OutboxEvent(
            event="member_changed",
            project_id=membership.project_id,
            payload={
                "action": "member.added",
                "user_id": str(user.id),
                "role": requested_role.value,
                "member": _member_read(user, new_membership).model_dump(mode="json"),
            },
        )
    ]
    if notification is not None:
        events.append(
            OutboxEvent(
                event="notification_created",
                project_id=membership.project_id,
                payload={
                    "recipient_id": str(notification.recipient_id),
                    "client_mutation_id": None,
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
    return (
        _member_read(user, new_membership),
        events,
    )


async def change_role(
    session: AsyncSession,
    *,
    membership: ProjectMember,
    actor_id: UUID,
    target_user_id: UUID,
    request: MemberRoleUpdate,
) -> tuple[MemberRead, list[OutboxEvent]]:
    target = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == membership.project_id,
            ProjectMember.user_id == target_user_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Project member not found.")
    require_action(
        membership,
        ProjectAction.MEMBER_CHANGE_ROLE,
        user_id=actor_id,
        target_role=target.role,
        target_user_id=target_user_id,
    )
    target_user = await session.get(User, target_user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="Project member not found.")
    new_role = ProjectRole(request.role)
    if target.role == new_role:
        return _member_read(target_user, target), []

    previous_role = target.role
    target.role = new_role
    session.add(
        ActivityLog(
            project_id=membership.project_id,
            actor_id=actor_id,
            action="member.role_changed",
            entity_type="member",
            entity_id=target_user_id,
            details={"from": previous_role.value, "to": new_role.value},
        )
    )
    try:
        await session.commit()
        await session.refresh(target)
    except Exception:
        await session.rollback()
        raise
    return (
        _member_read(target_user, target),
        [
            OutboxEvent(
                event="member_changed",
                project_id=membership.project_id,
                payload={
                    "action": "member.role_changed",
                    "user_id": str(target_user_id),
                    "from": previous_role.value,
                    "to": new_role.value,
                    "member": _member_read(target_user, target).model_dump(mode="json"),
                },
            )
        ],
    )


async def remove_member(
    session: AsyncSession,
    *,
    membership: ProjectMember,
    actor_id: UUID,
    target_user_id: UUID,
) -> list[OutboxEvent]:
    target = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == membership.project_id,
            ProjectMember.user_id == target_user_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Project member not found.")
    require_action(
        membership,
        ProjectAction.MEMBER_REMOVE,
        user_id=actor_id,
        target_role=target.role,
        target_user_id=target_user_id,
    )

    changed_task_ids: list[UUID] = []
    try:
        if target.role != ProjectRole.OWNER:
            await lock_project_tasks(session, membership.project_id)
            affected_tasks = list(
                (
                    await session.scalars(
                        select(Task)
                        .where(
                            Task.project_id == membership.project_id,
                            or_(
                                Task.assigned_to == target_user_id,
                                Task.reviewer_id == target_user_id,
                                Task.completed_by == target_user_id,
                            ),
                        )
                        .order_by(Task.id)
                        .with_for_update()
                    )
                ).all()
            )
            for task in affected_tasks:
                values: dict[str, object] = {
                    "version": Task.version + 1,
                    "updated_at": func.now(),
                }
                if task.assigned_to == target_user_id:
                    values["assigned_to"] = None
                    session.add(
                        ActivityLog(
                            project_id=membership.project_id,
                            actor_id=actor_id,
                            action="task.unassigned",
                            entity_type="task",
                            entity_id=task.id,
                            details={"reason": "member.removed"},
                        )
                    )
                if task.reviewer_id == target_user_id:
                    values["reviewer_id"] = None
                    session.add(
                        ActivityLog(
                            project_id=membership.project_id,
                            actor_id=actor_id,
                            action="task.reviewer_removed",
                            entity_type="task",
                            entity_id=task.id,
                            details={
                                "reason": "member.removed",
                                "reviewer_id": str(target_user_id),
                            },
                        )
                    )
                if task.completed_by == target_user_id:
                    values["completed_by"] = None
                    session.add(
                        ActivityLog(
                            project_id=membership.project_id,
                            actor_id=actor_id,
                            action="task.completion_credit_removed",
                            entity_type="task",
                            entity_id=task.id,
                            details={
                                "reason": "member.removed",
                                "completed_by": str(target_user_id),
                            },
                        )
                    )
                await session.execute(
                    update(Task).where(Task.id == task.id).values(**values)
                )
                changed_task_ids.append(task.id)
        session.add(
            ActivityLog(
                project_id=membership.project_id,
                actor_id=actor_id,
                action="member.removed",
                entity_type="member",
                entity_id=target_user_id,
                details={"role": target.role.value},
            )
        )
        notification = None
        if target_user_id != actor_id:
            notification = Notification(
                id=uuid4(),
                recipient_id=target_user_id,
                project_id=membership.project_id,
                actor_id=actor_id,
                type="member_removed",
                payload={"project_id": str(membership.project_id)},
            )
            session.add(notification)
        await session.delete(target)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    events = [
        OutboxEvent(
            event="member_changed",
            project_id=membership.project_id,
            payload={
                "action": "member.removed",
                "user_id": str(target_user_id),
                "role": target.role.value,
            },
        )
    ]
    if notification is not None:
        events.append(
            OutboxEvent(
                event="notification_created",
                project_id=membership.project_id,
                payload={
                    "recipient_id": str(notification.recipient_id),
                    "client_mutation_id": None,
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
    for task_id in changed_task_ids:
        task_read = await _load_task(session, task_id)
        if task_read is None:
            raise RuntimeError("Updated task could not be reloaded.")
        events.append(
            OutboxEvent(
                event="task_changed",
                project_id=membership.project_id,
                payload={
                    "action": "task.updated",
                    "task_id": str(task_id),
                    "version": task_read.version,
                    "task": task_read.model_dump(mode="json"),
                },
            )
        )
    return events
