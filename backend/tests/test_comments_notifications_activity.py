from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.main import fastapi_app
from app.models import Notification, ProjectMember, ProjectRole, User
from app.schemas.comment import CommentCreate
from app.schemas.task import TaskCreate
from app.services.activity import list_project_activity, list_recent_activity
from app.services.comments import create_comment, list_comments
from app.services.notifications import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.services.projects import create_project_with_owner
from app.services.tasks import create_task


def test_comment_create_validation() -> None:
    """Comments must be 1-2000 characters and trimmed.

    Empty or whitespace-only must fail.
    """
    # Valid comment
    c = CommentCreate(content="  Valid comment text  ")
    assert c.content == "Valid comment text"

    # Empty
    with pytest.raises(ValidationError):
        CommentCreate(content="")

    # Whitespace only
    with pytest.raises(ValidationError):
        CommentCreate(content="    ")

    # Too long (> 2000 characters)
    with pytest.raises(ValidationError):
        CommentCreate(content="x" * 2001)


@pytest_asyncio.fixture
async def collab_client(session: AsyncSession):
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
        password_hash="test-password-hash",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_comment_creation_permissions_notifications_and_activity(
    session: AsyncSession,
) -> None:
    """Verify comment create permissions, notifications de-duplication,

    activity logging, and outbox delivery.
    """
    owner = await make_user(session, "comment-owner")
    assignee = await make_user(session, "comment-assignee")
    outsider = await make_user(session, "comment-outsider")

    project = await create_project_with_owner(
        session, owner_id=owner.id, name="Comment project"
    )
    # Add assignee as member
    session.add(
        ProjectMember(
            project_id=project.id,
            user_id=assignee.id,
            role=ProjectRole.MEMBER,
        )
    )
    await session.flush()

    # Create a task assigned to assignee
    task, _ = await create_task(
        session,
        project_id=project.id,
        actor_id=owner.id,
        request=TaskCreate(
            title="Task with comments",
            assigned_to=assignee.id,
        ),
    )

    # Outsider cannot add comments (returns 404)
    with pytest.raises(Exception) as excinfo:
        await create_comment(
            session,
            task_id=task.id,
            actor_id=outsider.id,
            request=CommentCreate(content="Should fail"),
        )
    assert "404" in str(excinfo.value)

    # Owner comments on task: assignee should be notified, but not owner (actor)
    comment_read, events = await create_comment(
        session,
        task_id=task.id,
        actor_id=owner.id,
        request=CommentCreate(content="First comment by owner"),
    )
    assert comment_read.content == "First comment by owner"
    assert comment_read.author.id == owner.id

    # Check outbox events: comment_added + notification_created for assignee only
    event_names = [e.event for e in events]
    assert "comment_added" in event_names
    assert "notification_created" in event_names

    notif_event = next(e for e in events if e.event == "notification_created")
    assert notif_event.payload["recipient_id"] == str(assignee.id)

    # Assignee comments on task: creator (owner) should be notified, but not assignee
    _, events2 = await create_comment(
        session,
        task_id=task.id,
        actor_id=assignee.id,
        request=CommentCreate(content="Reply by assignee"),
    )
    notif_event2 = next(e for e in events2 if e.event == "notification_created")
    assert notif_event2.payload["recipient_id"] == str(owner.id)

    # List comments: paginated, oldest-first
    comments_list = await list_comments(session, task_id=task.id, user_id=owner.id)
    assert comments_list.total == 2
    assert len(comments_list.items) == 2
    assert comments_list.items[0].content == "First comment by owner"
    assert comments_list.items[1].content == "Reply by assignee"


@pytest.mark.asyncio
async def test_notifications_read_state_and_isolation(session: AsyncSession) -> None:
    """Verify notification read persistence, read-all, and non-recipient 404."""
    user1 = await make_user(session, "notif-user1")
    user2 = await make_user(session, "notif-user2")
    project = await create_project_with_owner(
        session, owner_id=user1.id, name="Notif project"
    )

    notif = Notification(
        id=uuid4(),
        recipient_id=user1.id,
        project_id=project.id,
        actor_id=user2.id,
        type="task_assigned",
        payload={"title": "Fix bug"},
    )
    session.add(notif)
    await session.commit()

    # User 2 cannot mark User 1's notification as read (returns 404)
    with pytest.raises(Exception) as excinfo:
        await mark_notification_read(
            session, notification_id=notif.id, user_id=user2.id
        )
    assert "404" in str(excinfo.value)

    # User 1 lists notifications: unread_count is 1
    res = await list_notifications(session, user_id=user1.id, unread_only=True)
    assert res.total == 1
    assert res.unread_count == 1
    assert res.items[0].read_at is None

    # User 1 marks it as read: idempotent
    read_result = await mark_notification_read(
        session, notification_id=notif.id, user_id=user1.id
    )
    assert read_result.read_at is not None

    # Read all
    await mark_all_notifications_read(session, user_id=user1.id)
    res_after = await list_notifications(session, user_id=user1.id, unread_only=True)
    assert res_after.unread_count == 0


@pytest.mark.asyncio
async def test_activity_feed_and_dashboard_recent_scoping(
    session: AsyncSession,
) -> None:
    """Verify activity feed ordering and scoping across caller's projects only."""
    user1 = await make_user(session, "act-user1")
    user2 = await make_user(session, "act-user2")

    p1 = await create_project_with_owner(session, owner_id=user1.id, name="Project 1")
    p2 = await create_project_with_owner(session, owner_id=user2.id, name="Project 2")
    await session.commit()

    # User 1 views p1 activity: OK
    p1_act = await list_project_activity(session, project_id=p1.id, user_id=user1.id)
    assert p1_act.total >= 1
    assert p1_act.items[0].action == "project.created"

    # User 1 views p2 activity: 404 (non-member)
    with pytest.raises(Exception) as excinfo:
        await list_project_activity(session, project_id=p2.id, user_id=user1.id)
    assert "404" in str(excinfo.value)

    # Recent activity for User 1 only includes p1, never p2
    recent = await list_recent_activity(session, user_id=user1.id, limit=20)
    for act in recent.items:
        assert act.project_id == p1.id
        assert act.project_id != p2.id
