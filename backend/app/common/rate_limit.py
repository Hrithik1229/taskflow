from collections import deque
from time import monotonic

from fastapi import HTTPException, Request, status

from app.config import settings


class SlidingWindowRateLimiter:
    max_buckets = 4096
    cleanup_interval = 64

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = {}
        self._checks = 0

    def reset(self) -> None:
        self._requests.clear()
        self._checks = 0

    def _remove_expired(self, now: float, window: int) -> None:
        expiry = now - window
        for key, entries in tuple(self._requests.items()):
            while entries and entries[0] <= expiry:
                entries.popleft()
            if not entries:
                del self._requests[key]

    def _make_room(self, now: float, window: int, required: int) -> None:
        if len(self._requests) + required <= self.max_buckets:
            return

        self._remove_expired(now, window)
        while len(self._requests) + required > self.max_buckets:
            oldest_key = min(
                self._requests,
                key=lambda key: self._requests[key][-1],
            )
            del self._requests[oldest_key]

    def check(self, action: str, client_ip: str, email: str) -> None:
        if not settings.AUTH_RATE_LIMIT_ENABLED:
            return

        now = monotonic()
        window = settings.AUTH_RATE_LIMIT_WINDOW_SECONDS
        limit = settings.AUTH_RATE_LIMIT_MAX_REQUESTS
        self._checks += 1
        if self._checks % self.cleanup_interval == 0:
            self._remove_expired(now, window)

        keys = (
            f"{action}:ip:{client_ip}",
            f"{action}:email:{email.strip().lower()}",
        )
        retry_after = 0
        for key in keys:
            entries = self._requests.get(key)
            if entries is None:
                continue
            while entries and entries[0] <= now - window:
                entries.popleft()
            if not entries:
                del self._requests[key]
                continue
            if len(entries) >= limit:
                retry_after = max(
                    retry_after,
                    max(1, int(window - (now - entries[0]))),
                )

        if retry_after:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        self._make_room(now, window, sum(key not in self._requests for key in keys))
        for key in keys:
            self._requests.setdefault(key, deque()).append(now)


rate_limiter = SlidingWindowRateLimiter()


def enforce_auth_rate_limit(request: Request, action: str, email: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    rate_limiter.check(action, client_ip, email)
