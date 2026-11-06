from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.main import fastapi_app
from app.models import (
    ActivityLog,
    Project,
    ProjectMember,
    ProjectRole,
    Task,
    TaskStatus,
    User,
)
from app.schemas.member import MemberAdd, MemberRoleUpdate
from app.schemas.project import ProjectCreate
from app.security.jwt import create_access_token
from app.security.permissions import get_membership
from app.services.members import add_member_by_email, change_role, remove_member
from app.services.projects import create_project


@pytest_asyncio.fixture
async def project_client(session: AsyncSession):
    async def override_session():
        yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        fastapi_app.dependency_overrides.pop(get_session, None)


async def make_user(session: AsyncSession, label: str) -> User:
    suffix = uuid4().hex
    user = User(
        username=f"{label}-{suffix[:8]}",
        email=f"{label}-{suffix}@example.com",
        password_hash="not-used-in-these-tests",
    )
    session.add(user)
    await session.flush()
    return user


def headers(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def create_project_request(
    client: AsyncClient,
    user: User,
    *,
    name: str = "Project",
) -> dict:
    response = await client.post(
        "/api/projects",
        json={"name": name, "description": "A test project"},
        headers=headers(user.id),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def add_member(
    client: AsyncClient,
    actor: User,
    project_id: str,
    target: User,
    role: str = "member",
):
    return await client.post(
        f"/api/projects/{project_id}/members",
        json={"email": target.email, "role": role},
        headers=headers(actor.id),
    )


@pytest.mark.asyncio
async def test_create_project_creates_owner_activity_and_outbox(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "owner")
    project, events = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="A project", description="Description"),
    )

    assert project.role == ProjectRole.OWNER
    assert project.member_count == 1
    assert len(events) == 1
    assert events[0].event == "project_changed"
    assert events[0].project_id == project.id
    assert events[0].payload["action"] == "project.created"
    assert events[0].payload["project"]["id"] == str(project.id)
    assert await session.scalar(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == owner.id,
            ProjectMember.role == ProjectRole.OWNER,
        )
    )
    activity = await session.scalar(
        select(ActivityLog).where(ActivityLog.project_id == project.id)
    )
    assert activity is not None
    assert activity.action == "project.created"


@pytest.mark.asyncio
async def test_project_creation_failure_rolls_back_project_membership_and_activity(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user(session, "rollback-owner")

    async def fail_commit():
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        await create_project(
            session,
            owner_id=owner.id,
            request=ProjectCreate(name="Atomic project"),
        )
    await session.rollback()

    assert (
        await session.scalar(
            select(func.count(Project.id)).where(Project.name == "Atomic project")
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(ProjectMember.id)).where(
                ProjectMember.user_id == owner.id
            )
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(ActivityLog.id)).where(ActivityLog.actor_id == owner.id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_member_services_record_activity_and_return_outbox_events(
    session: AsyncSession,
) -> None:
    owner = await make_user(session, "outbox-owner")
    invited = await make_user(session, "outbox-invited")
    project, _ = await create_project(
        session,
        owner_id=owner.id,
        request=ProjectCreate(name="Outbox project"),
    )
    owner_membership = await get_membership(session, project.id, owner.id)
    assert owner_membership is not None

    _, added_events = await add_member_by_email(
        session,
        membership=owner_membership,
        actor_id=owner.id,
        request=MemberAdd(email=invited.email),
    )
    assert len(added_events) == 1
    assert added_events[0].event == "member_changed"
    assert added_events[0].project_id == project.id
    assert added_events[0].payload["action"] == "member.added"
    assert added_events[0].payload["user_id"] == str(invited.id)
    assert added_events[0].payload["role"] == ProjectRole.MEMBER.value
    assert added_events[0].payload["member"]["username"] == invited.username

    _, changed_events = await change_role(
        session,
        membership=owner_membership,
        actor_id=owner.id,
        target_user_id=invited.id,
        request=MemberRoleUpdate(role=ProjectRole.ADMIN),
    )
    assert len(changed_events) == 1
    assert changed_events[0].event == "member_changed"
    assert changed_events[0].payload["action"] == "member.role_changed"
    assert changed_events[0].payload["user_id"] == str(invited.id)
    assert changed_events[0].payload["from"] == ProjectRole.MEMBER.value
    assert changed_events[0].payload["to"] == ProjectRole.ADMIN.value
    assert changed_events[0].payload["member"]["role"] == ProjectRole.ADMIN.value

    removed_events = await remove_member(
        session,
        membership=owner_membership,
        actor_id=owner.id,
        target_user_id=invited.id,
    )
    assert len(removed_events) == 1
    assert removed_events[0].event == "member_changed"
    assert removed_events[0].payload["action"] == "member.removed"
    assert removed_events[0].payload["user_id"] == str(invited.id)

    activities = (
        await session.scalars(
            select(ActivityLog.action)
            .where(ActivityLog.project_id == project.id)
            .order_by(ActivityLog.created_at, ActivityLog.action)
        )
    ).all()
    assert {
        "project.created",
        "member.added",
        "member.role_changed",
        "member.removed",
    } <= set(activities)


@pytest.mark.asyncio
async def test_project_list_is_membership_scoped_and_paginated(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "list-owner")
    member = await make_user(session, "list-member")
    first = await create_project_request(project_client, owner, name="First")
    second = await create_project_request(project_client, owner, name="Second")
    third = await create_project_request(project_client, owner, name="Third")
    added = await add_member(project_client, owner, second["id"], member)
    assert added.status_code == 201

    owner_projects = await project_client.get(
        "/api/projects?offset=1&limit=1",
        headers=headers(owner.id),
    )
    member_projects = await project_client.get(
        "/api/projects",
        headers=headers(member.id),
    )

    assert owner_projects.status_code == 200
    assert len(owner_projects.json()) == 1
    assert member_projects.status_code == 200
    assert [entry["id"] for entry in member_projects.json()] == [second["id"]]
    assert {first["id"], third["id"]}.isdisjoint(
        entry["id"] for entry in member_projects.json()
    )


@pytest.mark.asyncio
async def test_project_detail_includes_real_zero_task_counts(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "detail-owner")
    project = await create_project_request(project_client, owner)

    response = await project_client.get(
        f"/api/projects/{project['id']}",
        headers=headers(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["task_counts"] == {
        "todo": 0,
        "in_progress": 0,
        "review": 0,
        "completed": 0,
    }


@pytest.mark.asyncio
async def test_project_detail_counts_tasks_from_database(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "task-count-owner")
    project = await create_project_request(project_client, owner)
    session.add_all(
        [
            Task(
                project_id=UUID(project["id"]),
                title="In progress",
                status=TaskStatus.IN_PROGRESS,
                created_by=owner.id,
            ),
            Task(
                project_id=UUID(project["id"]),
                title="Done",
                status=TaskStatus.COMPLETED,
                created_by=owner.id,
            ),
        ]
    )
    await session.flush()

    response = await project_client.get(
        f"/api/projects/{project['id']}",
        headers=headers(owner.id),
    )

    assert response.status_code == 200
    assert response.json()["task_counts"] == {
        "todo": 0,
        "in_progress": 1,
        "review": 0,
        "completed": 1,
    }


@pytest.mark.asyncio
async def test_non_member_gets_404_for_project_and_member_resources(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "private-owner")
    stranger = await make_user(session, "stranger")
    project = await create_project_request(project_client, owner)
    project_id = project["id"]
    auth = headers(stranger.id)

    responses = [
        await project_client.get(f"/api/projects/{project_id}", headers=auth),
        await project_client.patch(
            f"/api/projects/{project_id}",
            json={"name": "Leaked"},
            headers=auth,
        ),
        await project_client.delete(f"/api/projects/{project_id}", headers=auth),
        await project_client.get(f"/api/projects/{project_id}/members", headers=auth),
        await project_client.post(
            f"/api/projects/{project_id}/members",
            json={"email": stranger.email},
            headers=auth,
        ),
        await project_client.patch(
            f"/api/projects/{project_id}/members/{owner.id}",
            json={"role": "admin"},
            headers=auth,
        ),
        await project_client.delete(
            f"/api/projects/{project_id}/members/{owner.id}",
            headers=auth,
        ),
    ]

    assert [response.status_code for response in responses] == [404] * len(responses)
    assert all(
        response.json()["detail"] == "Project not found." for response in responses
    )


@pytest.mark.asyncio
async def test_only_owner_can_update_or_delete_project(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "manage-owner")
    admin = await make_user(session, "manage-admin")
    member = await make_user(session, "manage-member")
    project = await create_project_request(project_client, owner)
    assert (
        await add_member(project_client, owner, project["id"], admin, "admin")
    ).status_code == 201
    assert (
        await add_member(project_client, owner, project["id"], member)
    ).status_code == 201

    for user in (admin, member):
        update = await project_client.patch(
            f"/api/projects/{project['id']}",
            json={"name": "Not allowed"},
            headers=headers(user.id),
        )
        delete = await project_client.delete(
            f"/api/projects/{project['id']}",
            headers=headers(user.id),
        )
        assert update.status_code == delete.status_code == 403

    updated = await project_client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "Updated"},
        headers=headers(owner.id),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated"
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.project_id == UUID(project["id"]),
            ActivityLog.action == "project.updated",
        )
    )

    deleted = await project_client.delete(
        f"/api/projects/{project['id']}",
        headers=headers(owner.id),
    )
    assert deleted.status_code == 204
    assert await session.get(Project, UUID(project["id"])) is None


@pytest.mark.asyncio
async def test_member_add_role_change_and_remove_policy(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "roles-owner")
    admin = await make_user(session, "roles-admin")
    member = await make_user(session, "roles-member")
    another = await make_user(session, "roles-another")
    project = await create_project_request(project_client, owner)
    project_id = project["id"]

    assert (
        await add_member(project_client, owner, project_id, admin, "admin")
    ).status_code == 201
    assert (
        await add_member(project_client, owner, project_id, member)
    ).status_code == 201

    unknown = await project_client.post(
        f"/api/projects/{project_id}/members",
        json={"email": "not-registered@example.com"},
        headers=headers(owner.id),
    )
    duplicate = await add_member(project_client, owner, project_id, member)
    admin_add_admin = await add_member(
        project_client, admin, project_id, another, "admin"
    )
    owner_add_owner = await add_member(
        project_client, owner, project_id, another, "owner"
    )
    admin_add_member = await add_member(project_client, admin, project_id, another)
    member_add_member = await add_member(project_client, member, project_id, another)

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "No registered user with that email."
    assert duplicate.status_code == 409
    assert admin_add_admin.status_code == 403
    assert owner_add_owner.status_code == 422
    assert admin_add_member.status_code == 201
    assert member_add_member.status_code == 403

    admin_role_change = await project_client.patch(
        f"/api/projects/{project_id}/members/{member.id}",
        json={"role": "admin"},
        headers=headers(admin.id),
    )
    owner_promote = await project_client.patch(
        f"/api/projects/{project_id}/members/{member.id}",
        json={"role": "admin"},
        headers=headers(owner.id),
    )
    assert admin_role_change.status_code == 403
    assert owner_promote.status_code == 200
    assert owner_promote.json()["role"] == "admin"

    owner_demote = await project_client.patch(
        f"/api/projects/{project_id}/members/{member.id}",
        json={"role": "member"},
        headers=headers(owner.id),
    )
    owner_change_owner = await project_client.patch(
        f"/api/projects/{project_id}/members/{owner.id}",
        json={"role": "admin"},
        headers=headers(owner.id),
    )
    owner_assign_owner_role = await project_client.patch(
        f"/api/projects/{project_id}/members/{member.id}",
        json={"role": "owner"},
        headers=headers(owner.id),
    )
    assert owner_demote.status_code == 200
    assert owner_change_owner.status_code == 403
    assert owner_assign_owner_role.status_code == 422

    admin_remove_admin = await project_client.delete(
        f"/api/projects/{project_id}/members/{member.id}",
        headers=headers(admin.id),
    )
    assert admin_remove_admin.status_code == 204
    admin_remove_owner = await project_client.delete(
        f"/api/projects/{project_id}/members/{owner.id}",
        headers=headers(admin.id),
    )
    assert admin_remove_owner.status_code == 403
    admin_change_admin = await project_client.patch(
        f"/api/projects/{project_id}/members/{admin.id}",
        json={"role": "member"},
        headers=headers(admin.id),
    )
    assert admin_change_admin.status_code == 403
    owner_remove_admin = await project_client.delete(
        f"/api/projects/{project_id}/members/{admin.id}",
        headers=headers(owner.id),
    )
    assert owner_remove_admin.status_code == 204
    assert await session.scalar(
        select(ActivityLog.id).where(
            ActivityLog.project_id == UUID(project_id),
            ActivityLog.action == "member.role_changed",
        )
    )


@pytest.mark.asyncio
async def test_member_can_leave_and_assigned_tasks_are_unassigned(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "leave-owner")
    member = await make_user(session, "leave-member")
    project = await create_project_request(project_client, owner)
    await add_member(project_client, owner, project["id"], member)
    task = Task(
        project_id=UUID(project["id"]),
        title="Assigned work",
        created_by=owner.id,
        assigned_to=member.id,
    )
    session.add(task)
    await session.flush()

    left = await project_client.delete(
        f"/api/projects/{project['id']}/members/{member.id}",
        headers=headers(member.id),
    )
    after_leave = await project_client.get(
        f"/api/projects/{project['id']}",
        headers=headers(member.id),
    )
    owner_leave = await project_client.delete(
        f"/api/projects/{project['id']}/members/{owner.id}",
        headers=headers(owner.id),
    )

    await session.refresh(task)
    assert left.status_code == 204
    assert after_leave.status_code == 404
    assert owner_leave.status_code == 403
    assert task.assigned_to is None


@pytest.mark.asyncio
async def test_member_list_hides_internal_fields(
    session: AsyncSession,
    project_client: AsyncClient,
) -> None:
    owner = await make_user(session, "listmembers-owner")
    project = await create_project_request(project_client, owner)

    response = await project_client.get(
        f"/api/projects/{project['id']}/members",
        headers=headers(owner.id),
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(owner.id)
    assert response.json()[0]["role"] == "owner"
    assert "password_hash" not in response.text
