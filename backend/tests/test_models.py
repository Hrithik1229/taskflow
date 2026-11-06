from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ActivityLog,
    Comment,
    Notification,
    Project,
    ProjectMember,
    ProjectRole,
    Task,
    User,
)
from app.services.projects import create_project_with_owner


def make_user(email: str) -> User:
    return User(
        id=uuid4(),
        username=email.split("@", maxsplit=1)[0],
        email=email,
        password_hash="argon2id-test-hash",
    )


def make_project(owner: User, name: str = "Test project") -> Project:
    return Project(id=uuid4(), name=name, owner_id=owner.id)


def make_task(project: Project, creator: User, **kwargs: object) -> Task:
    return Task(
        id=uuid4(),
        project_id=project.id,
        title="Test task",
        created_by=creator.id,
        **kwargs,
    )


async def flush_in_savepoint(session: AsyncSession, *objects: object) -> None:
    async with session.begin_nested():
        session.add_all(objects)
        await session.flush()


@pytest.mark.asyncio
async def test_email_must_be_unique(session: AsyncSession) -> None:
    first = make_user("same@example.test")
    second = make_user("same@example.test")
    session.add(first)
    await session.flush()

    with pytest.raises(IntegrityError):
        await flush_in_savepoint(session, second)


@pytest.mark.asyncio
async def test_email_must_be_normalized(session: AsyncSession) -> None:
    with pytest.raises(IntegrityError):
        await flush_in_savepoint(session, make_user("Uppercase@example.test"))


@pytest.mark.asyncio
async def test_project_membership_pair_must_be_unique(session: AsyncSession) -> None:
    owner = make_user("owner@example.test")
    member = make_user("member@example.test")
    project = make_project(owner)
    session.add_all([owner, member])
    await session.flush()
    session.add(project)
    await session.flush()
    session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=member.id,
            role=ProjectRole.MEMBER,
        )
    )
    await session.flush()

    duplicate = ProjectMember(
        id=uuid4(),
        project_id=project.id,
        user_id=member.id,
        role=ProjectRole.ADMIN,
    )
    with pytest.raises(IntegrityError):
        await flush_in_savepoint(session, duplicate)


@pytest.mark.asyncio
async def test_project_can_have_at_most_one_owner_membership(
    session: AsyncSession,
) -> None:
    owner = make_user("owner@example.test")
    second_owner = make_user("second-owner@example.test")
    project = make_project(owner)
    session.add_all([owner, second_owner])
    await session.flush()
    session.add(project)
    await session.flush()
    session.add(
        ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=owner.id,
            role=ProjectRole.OWNER,
        )
    )
    await session.flush()

    duplicate_owner = ProjectMember(
        id=uuid4(),
        project_id=project.id,
        user_id=second_owner.id,
        role=ProjectRole.OWNER,
    )
    with pytest.raises(IntegrityError):
        await flush_in_savepoint(session, duplicate_owner)


@pytest.mark.asyncio
async def test_project_creation_adds_owner_membership(session: AsyncSession) -> None:
    owner = make_user("service-owner@example.test")
    session.add(owner)
    await session.flush()

    project = await create_project_with_owner(
        session,
        owner_id=owner.id,
        name="Service-created project",
    )
    membership = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == owner.id,
        )
    )

    assert project.owner_id == owner.id
    assert membership is not None
    assert membership.role == ProjectRole.OWNER
    activity = await session.scalar(
        select(ActivityLog).where(
            ActivityLog.project_id == project.id,
            ActivityLog.action == "project.created",
        )
    )
    assert activity is not None


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("role", "observer"),
        ("status", "blocked"),
        ("priority", "critical"),
    ],
)
@pytest.mark.asyncio
async def test_enum_values_are_rejected(
    session: AsyncSession,
    field: str,
    invalid_value: str,
) -> None:
    owner = make_user("enum-owner@example.test")
    project = make_project(owner)
    if field == "role":
        entry = ProjectMember(
            id=uuid4(),
            project_id=project.id,
            user_id=owner.id,
            role=invalid_value,  # type: ignore[arg-type]
        )
    else:
        task_values: dict[str, object] = {field: invalid_value}
        entry = make_task(project, owner, **task_values)
    session.add(owner)
    await session.flush()
    session.add(project)
    await session.flush()

    with pytest.raises(DBAPIError):
        await flush_in_savepoint(session, entry)


@pytest.mark.parametrize(("position", "version"), [(-1, 1), (0, 0)])
@pytest.mark.asyncio
async def test_task_position_and_version_checks(
    session: AsyncSession,
    position: int,
    version: int,
) -> None:
    owner = make_user("checks-owner@example.test")
    project = make_project(owner)
    session.add(owner)
    await session.flush()
    session.add(project)
    await session.flush()

    task = make_task(project, owner, position=position, version=version)
    with pytest.raises(IntegrityError):
        await flush_in_savepoint(session, task)


@pytest.mark.asyncio
async def test_deleting_project_cascades_project_data(session: AsyncSession) -> None:
    owner = make_user("cascade-owner@example.test")
    project = make_project(owner)
    task = make_task(project, owner)
    membership = ProjectMember(
        id=uuid4(),
        project_id=project.id,
        user_id=owner.id,
        role=ProjectRole.OWNER,
    )
    comment = Comment(
        id=uuid4(),
        task_id=task.id,
        user_id=owner.id,
        content="A comment",
    )
    activity = ActivityLog(
        id=uuid4(),
        project_id=project.id,
        actor_id=owner.id,
        action="created",
        entity_type="task",
        entity_id=task.id,
        details={"source": "test"},
    )
    notification = Notification(
        id=uuid4(),
        recipient_id=owner.id,
        project_id=project.id,
        actor_id=owner.id,
        type="task_assigned",
        payload={"task_id": str(task.id)},
    )
    session.add(owner)
    await session.flush()
    session.add(project)
    await session.flush()
    session.add_all([membership, task])
    await session.flush()
    session.add_all([comment, activity, notification])
    await session.flush()

    await session.delete(project)
    await session.flush()

    assert await session.scalar(select(Task.id).where(Task.id == task.id)) is None
    assert (
        await session.scalar(
            select(ProjectMember.id).where(ProjectMember.id == membership.id)
        )
        is None
    )
    assert (
        await session.scalar(select(Comment.id).where(Comment.id == comment.id)) is None
    )
    assert (
        await session.scalar(
            select(ActivityLog.id).where(ActivityLog.id == activity.id)
        )
        is None
    )
    assert (
        await session.scalar(
            select(Notification.id).where(Notification.id == notification.id)
        )
        is None
    )


@pytest.mark.asyncio
async def test_user_with_owned_project_cannot_be_deleted(
    session: AsyncSession,
) -> None:
    owner = make_user("restrict-owner@example.test")
    project = make_project(owner)
    session.add(owner)
    await session.flush()
    session.add(project)
    await session.flush()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await session.delete(owner)
            await session.flush()


@pytest.mark.asyncio
async def test_assignee_delete_unassigns_task(session: AsyncSession) -> None:
    owner = make_user("task-owner@example.test")
    assignee = make_user("assignee@example.test")
    project = make_project(owner)
    task = make_task(project, owner, assigned_to=assignee.id)
    session.add_all([owner, assignee])
    await session.flush()
    session.add(project)
    await session.flush()
    session.add(task)
    await session.flush()

    await session.delete(assignee)
    await session.flush()
    await session.refresh(task)

    assert task.assigned_to is None


@pytest.mark.asyncio
async def test_timestamps_are_timezone_aware(session: AsyncSession) -> None:
    user = make_user("time-owner@example.test")
    project = make_project(user)
    task = make_task(
        project,
        user,
        due_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(user)
    await session.flush()
    session.add(project)
    await session.flush()
    session.add(task)
    await session.flush()
    await session.refresh(user)
    await session.refresh(task)
    reloaded = await session.scalar(select(User).where(User.id == user.id))

    assert user.created_at.tzinfo is not None
    assert user.created_at.utcoffset() == timedelta(0)
    assert task.due_at is not None and task.due_at.tzinfo is not None
    assert task.due_at.utcoffset() == timedelta(0)
    assert reloaded is not None and reloaded.created_at.tzinfo is not None
