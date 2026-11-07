import pytest
from httpx import ASGITransport, AsyncClient
from starlette.routing import Route

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
    """Extract (method, path) for all HTTP routes in the FastAPI application."""
    routes: list[tuple[str, str]] = []
    for route in fastapi_app.routes:
        if isinstance(route, Route):
            path = route.path
            for method in route.methods or []:
                if method in {"GET", "POST", "PATCH", "PUT", "DELETE"}:
                    routes.append((method, path))
    return sorted(routes)


def test_no_unprotected_route_without_allowlist() -> None:
    """Guard test: every API route must either be explicitly allowlisted for

    anonymous access or require authentication. Fails if a new endpoint is added
    without explicit review.
    """
    for method, path in get_api_routes():
        if path.startswith("/api/"):
            # Check whether it's either in the allowlist or covered by dependencies
            is_allowlisted = path in ALLOWLISTED_ANONYMOUS_PATHS
            # Find the matching route object
            matching = [
                r
                for r in fastapi_app.routes
                if isinstance(r, Route)
                and r.path == path
                and method in (r.methods or [])
            ]
            assert matching, f"No matching route found for {method} {path}"
            route_obj = matching[0]

            if not is_allowlisted:
                # Inspect dependencies to verify authentication requirement
                endpoint_func = route_obj.endpoint
                dependencies = getattr(route_obj, "dependencies", []) or []
                # Also check route-level dependencies or endpoint parameter dependencies
                has_security = False
                for dep in dependencies:
                    dep_name = getattr(dep.dependency, "__name__", "")
                    if "user" in dep_name.lower() or "auth" in dep_name.lower():
                        has_security = True
                        break

                # Also check function signatures
                import inspect

                sig = inspect.signature(endpoint_func)
                for param in sig.parameters.values():
                    param_type_str = str(param.annotation).lower()
                    param_default_str = str(param.default).lower()
                    if (
                        "user" in param_type_str
                        or "userdependency" in param_type_str
                        or "get_current_user" in param_default_str
                    ):
                        has_security = True
                        break

                assert has_security, (
                    f"Route {method} {path} is not in ALLOWLISTED_ANONYMOUS_PATHS "
                    f"and does not appear to require authentication."
                )


@pytest.mark.asyncio
async def test_anonymous_requests_to_protected_routes_return_401() -> None:
    """Verify that calling protected endpoints without credentials rejects with 401."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        # Test a representative sample of protected endpoints across all feature routers
        protected_endpoints = [
            ("GET", "/api/auth/me"),
            ("GET", "/api/projects"),
            ("POST", "/api/projects"),
            ("GET", "/api/projects/00000000-0000-0000-0000-000000000000"),
            ("GET", "/api/projects/00000000-0000-0000-0000-000000000000/tasks"),
            ("POST", "/api/projects/00000000-0000-0000-0000-000000000000/tasks"),
            ("GET", "/api/tasks/00000000-0000-0000-0000-000000000000"),
            ("PATCH", "/api/tasks/00000000-0000-0000-0000-000000000000"),
            ("DELETE", "/api/tasks/00000000-0000-0000-0000-000000000000"),
            ("GET", "/api/tasks/00000000-0000-0000-0000-000000000000/comments"),
            ("POST", "/api/tasks/00000000-0000-0000-0000-000000000000/comments"),
            ("GET", "/api/dashboard/summary"),
            ("GET", "/api/notifications"),
            ("PATCH", "/api/notifications/00000000-0000-0000-0000-000000000000/read"),
            ("PATCH", "/api/notifications/read-all"),
            ("GET", "/api/activity/recent"),
            ("GET", "/api/projects/00000000-0000-0000-0000-000000000000/activity"),
        ]

        for method, path in protected_endpoints:
            response = await client.request(method, path)
            msg = (
                f"Expected 401 for anonymous {method} {path}, "
                f"got {response.status_code}"
            )
            assert response.status_code == 401, msg
            data = response.json()
            assert "detail" in data
            assert data.get("code") == "http_401"
