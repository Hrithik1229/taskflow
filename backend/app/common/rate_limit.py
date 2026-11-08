from datetime import timedelta
from hashlib import sha256
from math import ceil

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AuthRateLimitAttempt


class PostgreSQLSlidingWindowRateLimiter:
    cleanup_interval = 64

    def __init__(self) -> None:
        self._checks = 0

    @staticmethod
    def _key_hash(action: str, kind: str, value: str) -> str:
        normalized = value.strip().lower() if kind == "email" else value
        return sha256(f"{action}:{kind}:{normalized}".encode()).hexdigest()

    async def check(
        self,
        session: AsyncSession,
        action: str,
        client_ip: str,
        email: str,
    ) -> None:
        if not settings.AUTH_RATE_LIMIT_ENABLED:
            return

        window = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS
        limit = settings.AUTH_RATE_LIMIT_MAX_REQUESTS
        key_hashes = sorted(
            {
                self._key_hash(action, "ip", client_ip),
                self._key_hash(action, "email", email),
            }
        )

        for key_hash in key_hashes:
            await session.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(key_hash, 0)))
            )

        cutoff = func.now() - timedelta(seconds=window)
        rows = (
            await session.execute(
                select(
                    AuthRateLimitAttempt.key_hash,
                    func.count().label("attempt_count"),
                    func.extract(
                        "epoch",
                        func.now() - func.min(AuthRateLimitAttempt.requested_at),
                    ).label("oldest_age_seconds"),
                )
                .where(
                    AuthRateLimitAttempt.key_hash.in_(key_hashes),
                    AuthRateLimitAttempt.requested_at >= cutoff,
                )
                .group_by(AuthRateLimitAttempt.key_hash)
            )
        ).all()

        retry_after = max(
            (
                max(1, ceil(window - float(oldest_age_seconds)))
                for _key_hash, attempt_count, oldest_age_seconds in rows
                if attempt_count >= limit
            ),
            default=0,
        )
        if retry_after:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        session.add_all(
            AuthRateLimitAttempt(key_hash=key_hash) for key_hash in key_hashes
        )
        self._checks += 1
        if self._checks % self.cleanup_interval == 0:
            await session.execute(
                delete(AuthRateLimitAttempt).where(
                    AuthRateLimitAttempt.requested_at
                    < func.now() - timedelta(seconds=window * 2)
                )
            )
        await session.commit()


rate_limiter = PostgreSQLSlidingWindowRateLimiter()


async def enforce_auth_rate_limit(
    session: AsyncSession,
    request: Request,
    action: str,
    email: str,
) -> None:
    client_ip = request.client.host if request.client else "unknown"
    await rate_limiter.check(session, action, client_ip, email)
