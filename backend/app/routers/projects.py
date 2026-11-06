from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ProjectMember, ProjectRole, User
from app.schemas.member import MemberAdd, MemberRead, MemberRoleUpdate
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.security.dependencies import get_current_user
from app.security.permissions import require_project_member, require_project_role
from app.services.members import (
    add_member_by_email,
    change_role,
    list_project_members,
    remove_member,
)
from app.services.projects import (
    create_project,
    delete_project,
    get_project,
    list_projects_for_user,
    update_project,
)
from app.sockets.emitters import publish_outbox_after_commit

router = APIRouter(prefix="/api/projects", tags=["projects"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
UserDependency = Annotated[User, Depends(get_current_user)]
MemberDependency = Annotated[ProjectMember, Depends(require_project_member)]
OwnerDependency = Annotated[
    ProjectMember, Depends(require_project_role(ProjectRole.OWNER))
]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: ProjectCreate,
    session: SessionDependency,
    user: UserDependency,
) -> ProjectRead:
    project, outbox = await create_project(
        session,
        owner_id=user.id,
        request=payload,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return project


@router.get("", response_model=list[ProjectRead])
async def list_mine(
    session: SessionDependency,
    user: UserDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ProjectRead]:
    return await list_projects_for_user(
        session,
        user_id=user.id,
        offset=offset,
        limit=limit,
    )


@router.get("/{project_id}", response_model=ProjectRead)
async def read_one(
    project_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    _membership: MemberDependency,
) -> ProjectRead:
    return await get_project(session, project_id=project_id, user_id=user.id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_one(
    payload: ProjectUpdate,
    session: SessionDependency,
    user: UserDependency,
    membership: OwnerDependency,
) -> ProjectRead:
    project, outbox = await update_project(
        session,
        membership=membership,
        actor_id=user.id,
        request=payload,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_one(
    session: SessionDependency,
    user: UserDependency,
    membership: OwnerDependency,
) -> Response:
    outbox = await delete_project(session, membership=membership, actor_id=user.id)
    await publish_outbox_after_commit(outbox, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/members", response_model=list[MemberRead])
async def list_members(
    membership: MemberDependency,
    session: SessionDependency,
) -> list[MemberRead]:
    return await list_project_members(session, project_id=membership.project_id)


@router.post(
    "/{project_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    payload: MemberAdd,
    session: SessionDependency,
    user: UserDependency,
    membership: MemberDependency,
) -> MemberRead:
    member, outbox = await add_member_by_email(
        session,
        membership=membership,
        actor_id=user.id,
        request=payload,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return member


@router.patch("/{project_id}/members/{user_id}", response_model=MemberRead)
async def update_member_role(
    user_id: UUID,
    payload: MemberRoleUpdate,
    session: SessionDependency,
    user: UserDependency,
    membership: MemberDependency,
) -> MemberRead:
    member, outbox = await change_role(
        session,
        membership=membership,
        actor_id=user.id,
        target_user_id=user_id,
        request=payload,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return member


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_member(
    user_id: UUID,
    session: SessionDependency,
    user: UserDependency,
    membership: MemberDependency,
) -> Response:
    outbox = await remove_member(
        session,
        membership=membership,
        actor_id=user.id,
        target_user_id=user_id,
    )
    await publish_outbox_after_commit(outbox, actor=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
