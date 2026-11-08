import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
import pytest_asyncio
import socketio
import uvicorn
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.database as database
from app.config import settings
from app.models import Project, ProjectMember, ProjectRole, Task, User
from app.security.jwt import create_access_token
from app.sockets import auth as socket_auth
from app.sockets import events as socket_events


@pytest_asyncio.fixture
async def realtime_environment(test_engine, monkeypatch):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionFactory", session_factory)
    monkeypatch.setattr(socket_auth, "SessionFactory", session_factory)
    monkeypatch.setattr(socket_events, "SessionFactory", session_factory)

    config = uvicorn.Config(
        "app.main:asgi_app",
        host="127.0.0.1",
        port=0,
        log_level="critical",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    try:
        for _ in range(500):
            if server.started:
                break
            if server_task.done():
                await server_task
            await asyncio.sleep(0.01)
        assert server.started, "Uvicorn did not start"
        port = server.servers[0].sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}", session_factory
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=10)


async def create_identity_fixture(session_factory):
    suffix = uuid4().hex
    owner = User(
        username=f"owner-{suffix[:8]}",
        email=f"owner-{suffix}@example.com",
        password_hash="not-used",
    )
    member = User(
        username=f"member-{suffix[:8]}",
        email=f"member-{suffix}@example.com",
        password_hash="not-used",
    )
    outsider = User(
        username=f"outsider-{suffix[:8]}",
        email=f"outsider-{suffix}@example.com",
        password_hash="not-used",
    )
    deleted = User(
        username=f"deleted-{suffix[:8]}",
        email=f"deleted-{suffix}@example.com",
        password_hash="not-used",
    )
    async with session_factory() as session:
        session.add_all([owner, member, outsider, deleted])
        await session.flush()
        project = Project(name="Realtime project", owner_id=owner.id)
        other_project = Project(name="Other realtime project", owner_id=outsider.id)
        session.add_all([project, other_project])
        await session.flush()
        session.add_all(
            [
                ProjectMember(
                    project_id=project.id,
                    user_id=owner.id,
                    role=ProjectRole.OWNER,
                ),
                ProjectMember(
                    project_id=project.id,
                    user_id=member.id,
                    role=ProjectRole.MEMBER,
                ),
                ProjectMember(
                    project_id=other_project.id,
                    user_id=outsider.id,
                    role=ProjectRole.OWNER,
                ),
            ]
        )
        await session.commit()
        ids = {
            "owner": owner.id,
            "member": member.id,
            "outsider": outsider.id,
            "deleted": deleted.id,
            "project": project.id,
            "other_project": other_project.id,
        }
        await session.delete(deleted)
        await session.commit()
    return ids


async def cleanup_identity_fixture(session_factory, ids):
    async with session_factory() as session:
        await session.execute(
            delete(Project).where(
                Project.id.in_([ids["project"], ids["other_project"]])
            )
        )
        await session.execute(
            delete(User).where(
                User.id.in_([ids["owner"], ids["member"], ids["outsider"]])
            )
        )
        await session.commit()


def expired_token(user_id) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


async def connect_client(url: str, user_id, event_queues=None):
    client = socketio.AsyncClient(reconnection=False)
    for event_name, event_queue in (event_queues or {}).items():

        async def receive(payload, queue=event_queue):
            await queue.put(payload)

        client.on(event_name, handler=receive)
    await client.connect(
        url,
        auth={"token": create_access_token(user_id)},
        transports=["websocket"],
    )
    return client


@pytest.mark.asyncio
async def test_socket_auth_rejects_bad_tokens_and_checks_expiry_on_join(
    realtime_environment,
    caplog: pytest.LogCaptureFixture,
) -> None:
    url, session_factory = realtime_environment
    ids = await create_identity_fixture(session_factory)

    client = None
    try:
        for auth in (
            {},
            {"token": "not-a-jwt"},
            {"token": expired_token(ids["owner"])},
        ):
            refused_client = socketio.AsyncClient(reconnection=False)
            with pytest.raises(socketio.exceptions.ConnectionError):
                await refused_client.connect(url, auth=auth, transports=["websocket"])

        deleted_client = socketio.AsyncClient(reconnection=False)
        with pytest.raises(socketio.exceptions.ConnectionError):
            await deleted_client.connect(
                url,
                auth={"token": create_access_token(ids["deleted"])},
                transports=["websocket"],
            )

        now = datetime.now(UTC)
        expiring_token = jwt.encode(
            {
                "sub": str(ids["owner"]),
                "iat": now,
                "exp": now + timedelta(seconds=5),
            },
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
        client = socketio.AsyncClient(reconnection=False)
        with caplog.at_level("DEBUG"):
            token = create_access_token(ids["owner"])
            await client.connect(
                url,
                auth={"token": token},
                transports=["websocket"],
            )
        assert token not in caplog.text
        await client.disconnect()
        client = socketio.AsyncClient(reconnection=False)
        await client.connect(
            url,
            auth={"token": expiring_token},
            transports=["websocket"],
        )
        await asyncio.sleep(5.1)
        ack = await client.call(
            "join_project",
            {"project_id": str(ids["project"])},
            timeout=2,
        )
        assert ack == {"ok": False, "error": "unauthenticated"}
    finally:
        if client and client.connected:
            await client.disconnect()
        await cleanup_identity_fixture(session_factory, ids)


@pytest.mark.asyncio
async def test_realtime_rooms_publish_committed_changes_and_revoke_removed_members(
    realtime_environment,
) -> None:
    url, session_factory = realtime_environment
    ids = await create_identity_fixture(session_factory)
    task_events = asyncio.Queue()
    update_events = asyncio.Queue()
    move_events = asyncio.Queue()
    delete_events = asyncio.Queue()
    member_changes = asyncio.Queue()
    removals = asyncio.Queue()
    notifications = asyncio.Queue()
    owner_notifications = asyncio.Queue()
    outsider_notifications = asyncio.Queue()
    owner_task_events = asyncio.Queue()
    member_client = await connect_client(
        url,
        ids["member"],
        {
            "task_created": task_events,
            "task_updated": update_events,
            "task_moved": move_events,
            "task_deleted": delete_events,
            "member_changed": member_changes,
            "removed_from_project": removals,
            "notification_created": notifications,
        },
    )
    outsider_events = asyncio.Queue()
    outsider_client = await connect_client(
        url,
        ids["outsider"],
        {
            "task_created": outsider_events,
            "notification_created": outsider_notifications,
        },
    )
    owner_client = await connect_client(
        url,
        ids["owner"],
        {
            "task_created": owner_task_events,
            "notification_created": owner_notifications,
        },
    )

    try:
        member_ack = await member_client.call(
            "join_project",
            {"project_id": str(ids["project"])},
            timeout=2,
        )
        assert member_ack == {"ok": True, "project_id": str(ids["project"])}
        owner_ack = await owner_client.call(
            "join_project",
            {"project_id": str(ids["project"])},
            timeout=2,
        )
        assert owner_ack == {"ok": True, "project_id": str(ids["project"])}
        denied_ack = await outsider_client.call(
            "join_project",
            {"project_id": str(ids["project"])},
            timeout=2,
        )
        assert denied_ack == {"ok": False, "error": "forbidden"}
        other_ack = await outsider_client.call(
            "join_project",
            {"project_id": str(ids["other_project"])},
            timeout=2,
        )
        assert other_ack["ok"] is True

        from sqlalchemy import event as sqlalchemy_event
        from sqlalchemy.ext.asyncio import AsyncSession

        commit_failure_raised = False

        def fail_first_commit(_session):
            nonlocal commit_failure_raised
            if not commit_failure_raised:
                commit_failure_raised = True
                raise RuntimeError("simulated commit failure")

        sqlalchemy_event.listen(
            AsyncSession.sync_session_class, "before_commit", fail_first_commit
        )
        try:
            async with httpx.AsyncClient(base_url=url) as http:
                failed_response = await http.post(
                    f"/api/projects/{ids['project']}/tasks",
                    json={"title": "Must roll back"},
                    headers={
                        "Authorization": (f"Bearer {create_access_token(ids['owner'])}")
                    },
                )
        finally:
            sqlalchemy_event.remove(
                AsyncSession.sync_session_class, "before_commit", fail_first_commit
            )
        assert failed_response.status_code == 500
        async with session_factory() as session:
            assert (
                await session.scalar(
                    select(Task.id).where(Task.title == "Must roll back")
                )
                is None
            )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task_events.get(), timeout=0.15)

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.post(
                f"/api/projects/{ids['project']}/tasks",
                json={
                    "title": "Committed from REST",
                    "assigned_to": str(ids["member"]),
                },
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}",
                    "X-Client-Mutation-Id": "realtime-test-mutation",
                },
            )
        assert response.status_code == 201, response.text
        task_event = await asyncio.wait_for(task_events.get(), timeout=3)
        assert task_event["type"] == "task_created"
        assert task_event["project_id"] == str(ids["project"])
        assert task_event["client_mutation_id"] == "realtime-test-mutation"
        assert task_event["task"]["version"] == 1
        assert task_event["task"]["status_changed_by"] is None
        assert task_event["task"]["completed_by"] is None
        assert task_event["actor"]["id"] == str(ids["owner"])
        assert task_event["event_id"]
        assert task_event["occurred_at"]
        assert "password_hash" not in str(task_event)
        async with session_factory() as session:
            committed_task_id = await session.scalar(
                select(Task.id).where(Task.id == response.json()["id"])
            )
        assert committed_task_id is not None
        owner_task_event = await asyncio.wait_for(owner_task_events.get(), timeout=3)
        assert owner_task_event["event_id"] == task_event["event_id"]
        assert owner_task_event["task"]["id"] == task_event["task"]["id"]
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(outsider_events.get(), timeout=0.15)

        notification = await asyncio.wait_for(notifications.get(), timeout=3)
        assert notification["type"] == "notification_created"
        assert (
            notification["notification"]["payload"]["task_id"] == response.json()["id"]
        )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(owner_notifications.get(), timeout=0.15)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(outsider_notifications.get(), timeout=0.15)

        task_id = response.json()["id"]
        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.patch(
                f"/api/tasks/{task_id}",
                json={"title": "Updated task", "expected_version": 1},
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}"
                },
            )
        assert response.status_code == 200
        updated_event = await asyncio.wait_for(update_events.get(), timeout=3)
        assert updated_event["task"]["version"] == 2
        assert updated_event["task"]["title"] == "Updated task"

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.patch(
                f"/api/tasks/{task_id}/move",
                json={
                    "status": "review",
                    "position": 0,
                    "expected_version": 2,
                    "reviewer_id": str(ids["member"]),
                },
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}"
                },
            )
        assert response.status_code == 200
        moved_event = await asyncio.wait_for(move_events.get(), timeout=3)
        assert moved_event["task"]["version"] == 3
        assert moved_event["task"]["status"] == "review"
        assert moved_event["task"]["reviewer"]["id"] == str(ids["member"])
        assert moved_event["task"]["review_requested_by"]["id"] == str(ids["owner"])
        assert moved_event["task"]["status_changed_by"]["id"] == str(ids["owner"])
        task_update_notification = await asyncio.wait_for(
            notifications.get(),
            timeout=3,
        )
        assert task_update_notification["notification"]["type"] == "task_updated"
        review_notification = await asyncio.wait_for(notifications.get(), timeout=3)
        assert review_notification["notification"]["type"] == "review_requested"

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.patch(
                f"/api/tasks/{task_id}/move",
                json={
                    "status": "completed",
                    "position": 0,
                    "expected_version": 3,
                },
                headers={
                    "Authorization": "Bearer " + create_access_token(ids["member"])
                },
            )
        assert response.status_code == 200
        completed_event = await asyncio.wait_for(move_events.get(), timeout=3)
        assert completed_event["task"]["version"] == 4
        assert completed_event["actor"]["id"] == str(ids["member"])
        assert completed_event["task"]["completed_by"]["id"] == str(ids["owner"])
        assert completed_event["task"]["completed_at"]
        completion_notification = await asyncio.wait_for(
            owner_notifications.get(),
            timeout=3,
        )
        assert completion_notification["notification"]["type"] == "review_completed"

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.delete(
                f"/api/tasks/{task_id}",
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}"
                },
            )
        assert response.status_code == 204
        deleted_event = await asyncio.wait_for(delete_events.get(), timeout=3)
        assert deleted_event["task"]["id"] == task_id
        assert deleted_event["task"]["version"] == 5

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.delete(
                f"/api/projects/{ids['project']}/members/{ids['member']}",
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}"
                },
            )
        assert response.status_code == 204, response.text
        changed = await asyncio.wait_for(member_changes.get(), timeout=3)
        assert changed["action"] == "member.removed"
        removed = await asyncio.wait_for(removals.get(), timeout=3)
        assert removed["project_id"] == str(ids["project"])

        async with httpx.AsyncClient(base_url=url) as http:
            response = await http.post(
                f"/api/projects/{ids['project']}/tasks",
                json={"title": "After removal"},
                headers={
                    "Authorization": f"Bearer {create_access_token(ids['owner'])}"
                },
            )
        assert response.status_code == 201, response.text
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task_events.get(), timeout=0.15)
        rejoin = await member_client.call(
            "join_project",
            {"project_id": str(ids["project"])},
            timeout=2,
        )
        assert rejoin == {"ok": False, "error": "forbidden"}
    finally:
        await member_client.disconnect()
        await outsider_client.disconnect()
        await owner_client.disconnect()
        await cleanup_identity_fixture(session_factory, ids)
