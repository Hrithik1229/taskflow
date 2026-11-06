import pytest
from fastapi import HTTPException

from app.common import rate_limit
from app.common.rate_limit import SlidingWindowRateLimiter
from app.config import settings


def test_blocked_new_emails_do_not_allocate_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = SlidingWindowRateLimiter()
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_MAX_REQUESTS", 1)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 10.0)

    limiter.check("login", "203.0.113.1", "first@example.com")
    for suffix in range(50):
        with pytest.raises(HTTPException) as error:
            limiter.check("login", "203.0.113.1", f"new-{suffix}@example.com")
        assert error.value.status_code == 429

    assert set(limiter._requests) == {
        "login:ip:203.0.113.1",
        "login:email:first@example.com",
    }


def test_periodic_cleanup_removes_expired_email_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = SlidingWindowRateLimiter()
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_MAX_REQUESTS", 100)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_WINDOW_SECONDS", 60)
    monkeypatch.setattr(rate_limit, "monotonic", lambda: 10.0)
    limiter.check("login", "203.0.113.1", "old@example.com")

    current_time = [71.0]
    monkeypatch.setattr(rate_limit, "monotonic", lambda: current_time[0])
    for index in range(limiter.cleanup_interval - 1):
        limiter.check("login", f"203.0.113.{index + 2}", f"user-{index}@example.com")

    assert "login:email:old@example.com" not in limiter._requests
