from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt

from app.config import settings


class AccessTokenError(Exception):
    """Raised when an access token is expired, malformed, or invalid."""


def _secret_key() -> str:
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")
    return settings.JWT_SECRET_KEY


def create_access_token(user_id: UUID | str) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if settings.JWT_ISSUER:
        claims["iss"] = settings.JWT_ISSUER
    if settings.JWT_AUDIENCE:
        claims["aud"] = settings.JWT_AUDIENCE
    return jwt.encode(claims, _secret_key(), algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> UUID:
    user_id, _ = decode_access_token_with_expiry(token)
    return user_id


def decode_access_token_with_expiry(token: str) -> tuple[UUID, datetime]:
    try:
        claims = jwt.decode(
            token,
            _secret_key(),
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={
                "require": ["sub", "exp", "iat"],
                "verify_iss": settings.JWT_ISSUER is not None,
                "verify_aud": settings.JWT_AUDIENCE is not None,
            },
        )
        expires_at = claims["exp"]
        if isinstance(expires_at, (int, float)):
            expiration = datetime.fromtimestamp(expires_at, UTC)
        elif isinstance(expires_at, datetime):
            expiration = expires_at.astimezone(UTC)
        else:
            raise TypeError("Invalid token expiration.")
        return UUID(claims["sub"]), expiration
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise AccessTokenError("Invalid or expired access token.") from exc
