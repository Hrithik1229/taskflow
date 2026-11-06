from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.rate_limit import rate_limiter
from app.config import settings
from app.database import get_session
from app.main import fastapi_app
from app.models import User
from app.security.jwt import create_access_token
from app.security.passwords import verify_password


@pytest.fixture(autouse=True)
def clear_rate_limiter() -> None:
    rate_limiter.reset()


@pytest.fixture
def payload() -> dict[str, str]:
    return {
        "username": "auth-user",
        "email": "auth@example.com",
        "password": "valid-password-123",
    }


@pytest.fixture
def override_database():
    @asynccontextmanager
    async def override(session: AsyncSession):
        async def get_test_session():
            yield session

        fastapi_app.dependency_overrides[get_session] = get_test_session
        try:
            yield
        finally:
            fastapi_app.dependency_overrides.pop(get_session, None)

    return override


@pytest_asyncio.fixture
async def auth_client(session: AsyncSession, override_database):
    async with override_database(session):
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_register_returns_public_user_and_hashes_password(
    auth_client: AsyncClient,
    session: AsyncSession,
    payload: dict[str, str],
) -> None:
    response = await auth_client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    result = response.json()
    assert result["username"] == payload["username"]
    assert result["email"] == payload["email"]
    assert "password_hash" not in response.text

    user = await session.get(User, result["id"])
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != payload["password"]
    assert verify_password(payload["password"], user.password_hash)


@pytest.mark.asyncio
async def test_register_normalizes_email_and_rejects_duplicate(
    auth_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    assert (
        await auth_client.post("/api/auth/register", json=payload)
    ).status_code == 201
    duplicate = {**payload, "email": "  AUTH@Example.COM "}

    response = await auth_client.post("/api/auth/register", json=duplicate)

    assert response.status_code == 409
    assert response.json()["code"] == "http_409"


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "valid", "email": "not-an-email", "password": "long-enough"},
        {"username": "valid", "email": "valid@example.com", "password": "short"},
        {"username": "ab", "email": "valid@example.com", "password": "long-enough"},
    ],
)
@pytest.mark.asyncio
async def test_register_validation_errors_return_422(
    auth_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    response = await auth_client.post("/api/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_login_returns_access_token_and_me_returns_public_profile(
    auth_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    await auth_client.post("/api/auth/register", json=payload)
    response = await auth_client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )

    assert response.status_code == 200
    token = response.json()
    assert token["token_type"] == "bearer"
    assert token["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert token["access_token"]

    profile = await auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["email"] == payload["email"]
    assert "password_hash" not in profile.text


@pytest.mark.asyncio
async def test_wrong_password_and_unknown_email_share_same_error(
    auth_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    await auth_client.post("/api/auth/register", json=payload)
    wrong_password = await auth_client.post(
        "/api/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )
    unknown_email = await auth_client.post(
        "/api/auth/login",
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


@pytest.mark.asyncio
async def test_me_without_token_is_unauthorized(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "http_401"


@pytest.mark.parametrize("token_kind", ["expired", "tampered", "malformed"])
@pytest.mark.asyncio
async def test_me_rejects_expired_and_tampered_tokens(
    auth_client: AsyncClient,
    payload: dict[str, str],
    token_kind: str,
) -> None:
    await auth_client.post("/api/auth/register", json=payload)
    if token_kind == "expired":
        now = datetime.now(UTC)
        token = jwt.encode(
            {"sub": str(uuid4()), "iat": now - timedelta(minutes=10), "exp": now},
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
        )
    elif token_kind == "tampered":
        token = jwt.encode(
            {
                "sub": str(uuid4()),
                "iat": datetime.now(UTC),
                "exp": datetime.now(UTC) + timedelta(minutes=5),
            },
            "not-the-configured-secret-long-enough-to-satisfy-hs256",
            algorithm=settings.JWT_ALGORITHM,
        )
    else:
        token = "not-a-jwt"

    response = await auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_me_rejects_token_for_deleted_user(
    auth_client: AsyncClient,
    session: AsyncSession,
    payload: dict[str, str],
) -> None:
    response = await auth_client.post("/api/auth/register", json=payload)
    token = create_access_token(response.json()["id"])
    user = await session.get(User, response.json()["id"])
    assert user is not None
    await session.delete(user)
    await session.commit()

    profile = await auth_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert profile.status_code == 401


@pytest.mark.asyncio
async def test_auth_rate_limit_returns_429_and_retry_after(
    auth_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_MAX_REQUESTS", 1)
    first = await auth_client.post(
        "/api/auth/login",
        json={"email": "throttle@example.com", "password": "not-a-password"},
    )
    second = await auth_client.post(
        "/api/auth/login",
        json={"email": "throttle@example.com", "password": "not-a-password"},
    )

    assert first.status_code == 401
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1
    assert second.json()["code"] == "http_429"
