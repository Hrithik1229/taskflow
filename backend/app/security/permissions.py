from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ProjectMember, ProjectRole, User
from app.security.dependencies import get_current_user


class ProjectAction(StrEnum):
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    MEMBER_ADD = "member.add"
    MEMBER_CHANGE_ROLE = "member.change_role"
    MEMBER_REMOVE = "member.remove"
    TASK_CREATE = "task.create"
    TASK_EDIT = "task.edit"
    TASK_DELETE = "task.delete"
    TASK_MOVE = "task.move"
    TASK_REVIEW_DECIDE = "task.review_decide"
    TASK_SET_REVIEWER = "task.set_reviewer"
    COMMENT_CREATE = "comment.create"
    ACTIVITY_VIEW = "activity.view"


SessionDependency = Annotated[AsyncSession, Depends(get_session)]


async def get_membership(
    session: AsyncSession,
    project_id: UUID,
    user_id: UUID,
) -> ProjectMember | None:
    return await session.scalar(
        select(ProjectMember)
        .where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
        .execution_options(populate_existing=True)
    )


def can_perform(
    role: ProjectRole | str,
    action: ProjectAction | str,
    *,
    resource_owner_id: UUID | None = None,
    assignee_id: UUID | None = None,
    user_id: UUID | None = None,
    reviewer_id: UUID | None = None,
    review_requested_by_id: UUID | None = None,
    target_role: ProjectRole | str | None = None,
    target_user_id: UUID | None = None,
) -> bool:
    try:
        normalized_role = ProjectRole(role)
        normalized_action = ProjectAction(action)
        normalized_target_role = (
            ProjectRole(target_role) if target_role is not None else None
        )
    except (TypeError, ValueError):
        return False

    if normalized_action in {
        ProjectAction.PROJECT_UPDATE,
        ProjectAction.PROJECT_DELETE,
    }:
        return normalized_role == ProjectRole.OWNER

    if normalized_action == ProjectAction.MEMBER_ADD:
        if normalized_target_role == ProjectRole.OWNER:
            return False
        return normalized_role == ProjectRole.OWNER or (
            normalized_role == ProjectRole.ADMIN
            and normalized_target_role in (None, ProjectRole.MEMBER)
        )

    if normalized_action == ProjectAction.MEMBER_CHANGE_ROLE:
        return (
            normalized_role == ProjectRole.OWNER
            and normalized_target_role != ProjectRole.OWNER
        )

    if normalized_action == ProjectAction.MEMBER_REMOVE:
        if normalized_target_role == ProjectRole.OWNER:
            return False
        if normalized_role == ProjectRole.OWNER:
            return True
        if normalized_role == ProjectRole.ADMIN:
            return normalized_target_role == ProjectRole.MEMBER
        return (
            normalized_role == ProjectRole.MEMBER
            and user_id is not None
            and target_user_id == user_id
        )

    if normalized_action in {
        ProjectAction.TASK_EDIT,
        ProjectAction.TASK_DELETE,
    }:
        return normalized_role in (ProjectRole.OWNER, ProjectRole.ADMIN) or (
            normalized_role == ProjectRole.MEMBER
            and user_id is not None
            and user_id in (resource_owner_id, assignee_id)
        )

    if normalized_action == ProjectAction.TASK_REVIEW_DECIDE:
        return normalized_role in (ProjectRole.OWNER, ProjectRole.ADMIN) or (
            normalized_role == ProjectRole.MEMBER
            and user_id is not None
            and reviewer_id == user_id
        )

    if normalized_action == ProjectAction.TASK_SET_REVIEWER:
        return normalized_role in (ProjectRole.OWNER, ProjectRole.ADMIN) or (
            normalized_role == ProjectRole.MEMBER
            and user_id is not None
            and user_id in (reviewer_id, review_requested_by_id)
        )

    return normalized_role in {
        ProjectRole.OWNER,
        ProjectRole.ADMIN,
        ProjectRole.MEMBER,
    } and normalized_action in {
        ProjectAction.TASK_CREATE,
        ProjectAction.TASK_MOVE,
        ProjectAction.COMMENT_CREATE,
        ProjectAction.ACTIVITY_VIEW,
    }


async def require_project_member(
    project_id: UUID,
    session: SessionDependency,
    user: Annotated[User, Depends(get_current_user)],
) -> ProjectMember:
    membership = await get_membership(session, project_id, user.id)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return membership


def require_project_role(
    *allowed_roles: ProjectRole | str,
) -> Callable[..., Awaitable[ProjectMember]]:
    roles = frozenset(ProjectRole(role) for role in allowed_roles)
    if not roles:
        raise ValueError("At least one project role must be allowed.")

    async def dependency(
        membership: Annotated[ProjectMember, Depends(require_project_member)],
    ) -> ProjectMember:
        if membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return membership

    return dependency


def require_action(
    membership: ProjectMember,
    action: ProjectAction,
    *,
    resource_owner_id: UUID | None = None,
    assignee_id: UUID | None = None,
    user_id: UUID | None = None,
    target_role: ProjectRole | None = None,
    target_user_id: UUID | None = None,
    reviewer_id: UUID | None = None,
    review_requested_by_id: UUID | None = None,
) -> None:
    if not can_perform(
        membership.role,
        action,
        resource_owner_id=resource_owner_id,
        assignee_id=assignee_id,
        user_id=user_id,
        target_role=target_role,
        target_user_id=target_user_id,
        reviewer_id=reviewer_id,
        review_requested_by_id=review_requested_by_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )
