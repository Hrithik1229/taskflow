import re
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import fastapi_app

ALLOWLISTED_ANONYMOUS_PATHS = {
    "/api/auth/register",
    "/api/auth/login",
    "/api/health",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}


def get_api_routes() -> list[tuple[str, str]]:
    """Extract concrete paths and methods from the complete FastAPI schema."""
    routes = []
    for path, operations in fastapi_app.openapi()["paths"].items():
        concrete_path = re.sub(r"\{[^}:]+(?::[^}]+)?\}", str(UUID(int=0)), path)
        routes.extend(
            (method.upper(), concrete_path)
            for method in operations
            if method in {"get", "post", "patch", "put", "delete"}
        )
    return sorted(routes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        (method, path)
        for method, path in get_api_routes()
        if path.startswith("/api/") and path not in ALLOWLISTED_ANONYMOUS_PATHS
    ],
)
async def test_every_protected_route_rejects_anonymous_requests(
    method: str,
    path: str,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        response = await client.request(method, path)
    assert response.status_code == 401, (
        f"Expected anonymous {method} {path} to return 401, got {response.status_code}"
    )
    assert response.json().get("code") == "http_401"
