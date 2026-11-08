from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.main import fastapi_app
from app.models import Notification, ProjectMember, ProjectRole, Task, User
from app.schemas.project import ProjectCreate
from app.security.jwt import create_access_token
from app.services.projects import create_project

ROLES = ("owner", "admin", "member", "nonmember")
ALL_ALLOWED = (200, 200, 200, 200)
PROJECT_MEMBER_READ = (200, 200, 200, 404)
PROJECT_OWNER_ONLY = (200, 403, 403, 404)
PROJECT_ADD_MEMBER = (201, 201, 403, 404)
MEMBER_DELETE = (204, 204, 204, 404)
TASK_WRITE = (200, 200, 403, 404)
TASK_DELETE = (204, 204, 403, 404)
TASK_CREATE = (201, 201, 201, 404)
TASK_MOVE = (200, 200, 200, 404)
COMMENT_CREATE = (201, 201, 201, 404)
PROJECT_DELETE = (204, 403, 403, 404)

ROLE_MATRIX = (
    ("GET", "/api/auth/me", None, ALL_ALLOWED),
    ("POST", "/api/projects", "create_project", (201, 201, 201, 201)),
    ("GET", "/api/projects", None, ALL_ALLOWED),
    ("GET", "/api/projects/{project_id}", None, PROJECT_MEMBER_READ),
    ("PATCH", "/api/projects/{project_id}", "update_project", PROJECT_OWNER_ONLY),
    ("DELETE", "/api/projects/{project_id}", None, PROJECT_DELETE),
    ("GET", "/api/projects/{project_id}/members", None, PROJECT_MEMBER_READ),
    ("POST", "/api/projects/{project_id}/members", "add_member", PROJECT_ADD_MEMBER),
    (
        "PATCH",
        "/api/projects/{project_id}/members/{user_id}",
        "change_member_role",
        PROJECT_OWNER_ONLY,
    ),
    (
        "DELETE",
        "/api/projects/{project_id}/members/{user_id}",
        None,
        MEMBER_DELETE,
    ),
    (
        "POST",
        "/api/projects/{project_id}/tasks",
        "create_task",
        TASK_CREATE,
    ),
    ("GET", "/api/projects/{project_id}/tasks", None, PROJECT_MEMBER_READ),
    ("GET", "/api/tasks/{task_id}", None, PROJECT_MEMBER_READ),
    ("PATCH", "/api/tasks/{task_id}", "update_task", TASK_WRITE),
    ("DELETE", "/api/tasks/{task_id}", None, TASK_DELETE),
    ("PATCH", "/api/tasks/{task_id}/move", "move_task", TASK_MOVE),
    ("GET", "/api/dashboard/summary", None, ALL_ALLOWED),
    ("GET", "/api/dashboard/summary/breakdown?metric=total", None, ALL_ALLOWED),
    ("GET", "/api/tasks/{task_id}/comments", None, PROJECT_MEMBER_READ),
    ("POST", "/api/tasks/{task_id}/comments", "create_comment", COMMENT_CREATE),
    ("GET", "/api/notifications", None, ALL_ALLOWED),
    (
        "PATCH",
        "/api/notifications/{notification_id}/read",
        None,
        ALL_ALLOWED,
    ),
    ("PATCH", "/api/notifications/read-all", None, ALL_ALLOWED),
    ("GET", "/api/projects/{project_id}/activity", None, PROJECT_MEMBER_READ),
    ("GET", "/api/activity/recent", None, ALL_ALLOWED),
)


def test_role_matrix_covers_every_protected_api_route() -> None:
    matrix_routes = {
        (method, path.split("?", maxsplit=1)[0])
        for method, path, _body, _statuses in ROLE_MATRIX
    }
    anonymous_routes = {
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/health"),
    }
    openapi_routes = {
        (method.upper(), path)
        for path, operations in fastapi_app.openapi()["paths"].items()
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
        and path.startswith("/api/")
        and (method.upper(), path) not in anonymous_routes
    }

    assert matrix_routes == openapi_routes


async def make_user(session: AsyncSession, label: str) -> User:
    suffix = uuid4().hex
    user = User(
        username=f"{label}-{suffix[:8]}",
        email=f"{label}-{suffix}@example.com",
        password_hash="unused-in-authorization-tests",
    )
    session.add(user)
    await session.flush()
    return user


@pytest_asyncio.fixture
async def role_context(session: AsyncSession):
    users = {role: await make_user(session, role) for role in ROLES}
    invitee = await make_user(session, "invitee")
    project, _outbox = await create_project(
        session,
        owner_id=users["owner"].id,
        request=ProjectCreate(name=f"Role matrix {uuid4().hex[:8]}"),
    )
    session.add_all(
        [
            ProjectMember(
                project_id=project.id,
                user_id=users["admin"].id,
                role=ProjectRole.ADMIN,
            ),
            ProjectMember(
                project_id=project.id,
                user_id=users["member"].id,
                role=ProjectRole.MEMBER,
            ),
        ]
    )
    task = Task(
        project_id=project.id,
        title="Authorization matrix task",
        created_by=users["owner"].id,
    )
    notifications = {
        role: Notification(
            recipient_id=user.id,
            project_id=project.id,
            actor_id=users["owner"].id,
            type="matrix_test",
            payload={},
        )
        for role, user in users.items()
    }
    session.add_all([task, *notifications.values()])
    await session.flush()
    return {
        "users": users,
        "invitee": invitee,
        "project": project,
        "task": task,
        "notifications": notifications,
    }


def role_headers(user_id: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


def request_data(body_name: str | None, context: dict) -> dict | None:
    if body_name == "create_project":
        return {"name": "Matrix-created project"}
    if body_name == "update_project":
        return {"name": "Renamed matrix project"}
    if body_name == "add_member":
        return {"email": context["invitee"].email, "role": "member"}
    if body_name == "change_member_role":
        return {"role": "admin"}
    if body_name == "create_task":
        return {"title": "Matrix-created task"}
    if body_name == "update_task":
        return {"title": "Updated by permitted role", "expected_version": 1}
    if body_name == "move_task":
        return {"status": "in_progress", "position": 0, "expected_version": 1}
    if body_name == "create_comment":
        return {"content": "Matrix comment"}
    return None


@pytest.mark.parametrize(
    ("method", "path_template", "body_name", "expected_statuses"),
    ROLE_MATRIX,
)
@pytest.mark.parametrize("role_index", range(len(ROLES)), ids=ROLES)
@pytest.mark.asyncio
async def test_project_route_permissions_for_each_role(
    session: AsyncSession,
    role_context: dict,
    method: str,
    path_template: str,
    body_name: str | None,
    expected_statuses: tuple[int, ...],
    role_index: int,
) -> None:
    role = ROLES[role_index]
    user = role_context["users"][role]
    project_id = role_context["project"].id
    task_id = role_context["task"].id
    notification_id = role_context["notifications"][role].id
    path = (
        path_template.replace("{project_id}", str(project_id))
        .replace("{task_id}", str(task_id))
        .replace("{user_id}", str(role_context["users"]["member"].id))
        .replace("{notification_id}", str(notification_id))
    )
    path, _, query = path.partition("?")
    if query:
        path = f"{path}?{query}"

    async def override_session():
        yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            response = await client.request(
                method,
                path,
                headers=role_headers(user.id),
                json=request_data(body_name, role_context),
            )
    finally:
        fastapi_app.dependency_overrides.pop(get_session, None)

    assert response.status_code == expected_statuses[role_index], (
        f"{role} {method} {path}: expected "
        f"{expected_statuses[role_index]}, got {response.status_code}: {response.text}"
    )
