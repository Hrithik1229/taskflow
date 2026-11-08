import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.rate_limit import PostgreSQLSlidingWindowRateLimiter
from app.config import settings
from app.models import AuthRateLimitAttempt


@pytest.mark.asyncio
async def test_auth_rate_limits_are_shared_between_instances(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    first_instance = PostgreSQLSlidingWindowRateLimiter()
    second_instance = PostgreSQLSlidingWindowRateLimiter()

    await first_instance.check(
        session,
        "login",
        "203.0.113.1",
        "shared@example.com",
    )
    with pytest.raises(HTTPException) as error:
        await second_instance.check(
            session,
            "login",
            "203.0.113.1",
            "shared@example.com",
        )

    assert error.value.status_code == 429
    records = list(
        (
            await session.scalars(
                select(AuthRateLimitAttempt).order_by(AuthRateLimitAttempt.key_hash)
            )
        ).all()
    )
    assert len(records) == 2
    assert all(len(record.key_hash) == 64 for record in records)


@pytest.mark.asyncio
async def test_auth_rate_limits_are_scoped_by_action(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    limiter = PostgreSQLSlidingWindowRateLimiter()

    await limiter.check(session, "login", "203.0.113.2", "same@example.com")
    await limiter.check(session, "register", "203.0.113.2", "same@example.com")
    with pytest.raises(HTTPException) as error:
        await limiter.check(session, "login", "203.0.113.2", "same@example.com")

    assert error.value.status_code == 429
