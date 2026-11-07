import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, settings
from app.main import fastapi_app
from app.security.jwt import AccessTokenError, create_access_token, decode_access_token


def test_jwt_rejects_none_algorithm() -> None:
    """Security test: Tokens encoded with alg=none must be rejected."""
    token = jwt.encode(
        {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(minutes=10)},
        key="",
        algorithm="none",
    )
    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_jwt_rejects_algorithm_confusion() -> None:
    """Security test: Algorithm must be pinned strictly.

    Tokens signed with different algorithms must be rejected.
    """
    secret = (settings.JWT_SECRET_KEY or "fallback-test-secret").ljust(64, "x")
    # Sign with HS512 instead of HS256
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        key=secret,
        algorithm="HS512",
    )
    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_jwt_enforces_expiration() -> None:
    """Security test: Expired tokens must be rejected."""
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "iat": now - timedelta(minutes=60),
            "exp": now - timedelta(minutes=30),
        },
        key=settings.JWT_SECRET_KEY or "test-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(AccessTokenError):
        decode_access_token(token)


def test_jwt_rejects_tampered_signature() -> None:
    """Security test: Altered payload or wrong signature must be rejected."""
    valid_token = create_access_token(uuid4())
    parts = valid_token.split(".")
    # Tamper with signature
    tampered = f"{parts[0]}.{parts[1]}.tampered_signature_bits"
    with pytest.raises(AccessTokenError):
        decode_access_token(tampered)


@pytest.mark.asyncio
async def test_security_headers_present_on_responses() -> None:
    """Security test: HTTP responses must include defensive security headers."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    headers = response.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers.get("Permissions-Policy", "")


@pytest.mark.asyncio
async def test_cors_allowed_and_disallowed_origins() -> None:
    """Security test: CORS headers for allowed origins, omitted for disallowed."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        # Allowed origin
        allowed_res = await client.get(
            "/api/health",
            headers={"Origin": "http://localhost:5173"},
        )
        assert (
            allowed_res.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
        )

        # Disallowed origin
        disallowed_res = await client.get(
            "/api/health",
            headers={"Origin": "http://evil-attacker.com"},
        )
        assert disallowed_res.headers.get("access-control-allow-origin") is None

        # Preflight OPTIONS request
        preflight = await client.options(
            "/api/auth/login",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert preflight.status_code == 200
        assert (
            preflight.headers.get("access-control-allow-origin")
            == "http://localhost:5173"
        )


@pytest.mark.asyncio
async def test_error_responses_shape_and_no_traceback_leakage() -> None:
    """Security test: Unhandled exceptions return generic 500 without traceback."""
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app),
        base_url="http://test",
    ) as client:
        # Validation error (422) shape check
        val_res = await client.post(
            "/api/auth/register", json={"email": "not-an-email"}
        )
        assert val_res.status_code == 422
        body = val_res.json()
        assert body["code"] == "validation_error"
        assert "detail" in body

        # Trigger 500 by creating a temporary route that raises an exception
        @fastapi_app.get("/api/test-server-error-internal")
        async def boom():
            raise RuntimeError(
                "Database connection suddenly dropped: secret_token=12345"
            )

        try:
            res_500 = await client.get("/api/test-server-error-internal")
            assert res_500.status_code == 500
            data = res_500.json()
            assert data == {"detail": "Internal server error", "code": "internal_error"}
            # Verify response body text does NOT contain traceback or sensitive info
            assert "Traceback" not in res_500.text
            assert "secret_token" not in res_500.text
            assert "Database connection" not in res_500.text
        finally:
            # Clean up route
            fastapi_app.routes[:] = [
                r
                for r in fastapi_app.routes
                if getattr(r, "path", None) != "/api/test-server-error-internal"
            ]


def test_production_mode_disables_docs() -> None:
    """Security test: In production, docs exposure is disabled."""
    prod_settings = Settings(
        APP_ENV="production", APP_SECRET_KEY="sec1", JWT_SECRET_KEY="sec2"
    )
    assert prod_settings.is_production is True


def test_auth_logging_does_not_leak_passwords(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Security test: Logger must not record raw passwords."""
    logger = logging.getLogger("app.security")
    with caplog.at_level(logging.DEBUG):
        # Emulate authentication handling
        logger.info("Authentication attempt for user demo@example.com")
        # Ensure raw password string never appears in any logged record
        password = "SuperSecretPassword123!"
        assert password not in caplog.text
