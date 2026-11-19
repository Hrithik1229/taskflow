from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known placeholder / example values that must NOT be used in production.
# Any secret that equals one of these (or is shorter than MIN_SECRET_LENGTH)
# will cause the app to refuse to start.
# ---------------------------------------------------------------------------
_PLACEHOLDER_PATTERNS = re.compile(
    r"replace.with|change.me|your.secret|example|placeholder|todo|fixme|xxx",
    re.IGNORECASE,
)
_MIN_SECRET_LENGTH = 32

# asyncpg does not understand libpq-style query parameters.  These must be
# stripped from the URL and re-expressed as connect_args or SSL context.
# channel_binding and application_name are silently ignored or raise errors.
_ASYNCPG_UNSUPPORTED_PARAMS = frozenset(
    {
        "sslmode",
        "channel_binding",
        "application_name",
        "options",
        "gssencmode",
        "target_session_attrs",
        "connect_timeout",
    }
)


def _normalize_postgres_url(url: str) -> str:
    """
    Normalize a Postgres connection URL for use with asyncpg / SQLAlchemy
    async driver.

    Transformations applied (in order):
    1. ``postgres://`` → ``postgresql+asyncpg://``
       ``postgresql://`` → ``postgresql+asyncpg://``
       (already-prefixed URLs are left untouched)
    2. Strip query parameters that asyncpg does not understand (sslmode,
       channel_binding, etc.).  ``sslmode=require`` / ``sslmode=verify-full``
       are translated to ``ssl=require`` / ``ssl=verify-full`` so SQLAlchemy
       can pass them through to asyncpg's ``ssl`` connect arg.
    3. All other unknown params are logged and dropped to avoid
       ``unexpected keyword argument`` errors at runtime.

    >>> _normalize_postgres_url(
    ...     "postgres://u:p@ep-cool-123.us-east-2.aws.neon.tech/db"
    ...     "?sslmode=require&channel_binding=require"
    ... )
    'postgresql+asyncpg://u:p@ep-cool-123.us-east-2.aws.neon.tech/db?ssl=require'

    >>> _normalize_postgres_url(
    ...     "postgresql+asyncpg://u:p@host/db?ssl=require"
    ... )
    'postgresql+asyncpg://u:p@host/db?ssl=require'
    """
    if not url:
        return url

    # Step 1 — scheme normalisation
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    # already postgresql+asyncpg:// — leave as-is

    # Step 2 — parse and clean query string
    parsed = urlparse(url)
    if not parsed.query:
        return url

    qs = parse_qs(parsed.query, keep_blank_values=True)
    cleaned: dict[str, list[str]] = {}

    # Map sslmode → ssl (asyncpg's keyword)
    if "sslmode" in qs:
        sslmode_val = qs.pop("sslmode")[0]
        # asyncpg accepts: disable, allow, prefer, require, verify-ca, verify-full
        cleaned["ssl"] = [sslmode_val]

    for key, values in qs.items():
        if key in _ASYNCPG_UNSUPPORTED_PARAMS:
            logger.debug(
                "DATABASE_URL: dropping unsupported asyncpg query param %r=%r",
                key,
                values,
            )
        else:
            cleaned[key] = values

    new_query = urlencode(cleaned, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_SECRET_KEY: str | None = None
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str | None = None
    JWT_AUDIENCE: str | None = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, ge=1)
    AUTH_RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT_MAX_REQUESTS: int = Field(default=10, ge=1)
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1)
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, ge=1_024)
    DATABASE_URL: str = ""
    TEST_DATABASE_URL: str = ""
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Connection-pool settings — tuned for a managed Postgres that may impose
    # a low connection cap (e.g. Neon free tier: ~10–20 connections per
    # project, shared across branches).
    #
    # pool_size=3: base pool kept alive.  Small enough that two deployments
    # running briefly in parallel (blue/green) don't exceed a 10-connection
    # limit.
    # max_overflow=2: allow up to 5 total connections under burst traffic.
    # pool_recycle=300: recycle connections every 5 min to avoid getting
    # disconnected by Neon's idle-connection trimmer or the database's
    # statement_timeout.
    # pool_pre_ping=True: validate that a recycled connection is still alive
    # before handing it to a request; avoids "server closed the connection"
    # errors after Neon scales to zero and back up.
    DB_POOL_SIZE: int = Field(default=3, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=2, ge=0)
    DB_POOL_RECYCLE: int = Field(default=300, ge=30)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def reject_wildcard_cors(cls, origins: str) -> str:
        if "*" in [origin.strip() for origin in origins.split(",")]:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; '*' is not allowed"
            )
        return origins

    @model_validator(mode="after")
    def require_secrets_outside_tests(self) -> Settings:
        if self.APP_ENV.lower() == "test":
            return self

        missing = [
            name
            for name, value in (
                ("APP_SECRET_KEY", self.APP_SECRET_KEY),
                ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"Missing required secret(s): {', '.join(missing)}. "
                "Set them in the environment or backend/.env."
            )

        # Production & staging: reject placeholder / weak secrets
        if self.APP_ENV.lower() in ("production", "staging"):
            for name, value in (
                ("APP_SECRET_KEY", self.APP_SECRET_KEY),
                ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
            ):
                assert value is not None  # already checked above
                if _PLACEHOLDER_PATTERNS.search(value):
                    raise ValueError(
                        f"{name} contains a placeholder value. "
                        "Generate a real secret: python -c "
                        '"import secrets; print(secrets.token_hex(32))"'
                    )
                if len(value) < _MIN_SECRET_LENGTH:
                    raise ValueError(
                        f"{name} is too short ({len(value)} chars); "
                        f"minimum is {_MIN_SECRET_LENGTH}."
                    )

            # True production CORS must use https; staging allows http for local testing
            if self.APP_ENV.lower() == "production":
                for origin in self.cors_origins_list:
                    if not origin.startswith("https://"):
                        raise ValueError(
                            f"CORS_ORIGINS in production must use https://; "
                            f"got: {origin!r}"
                        )

        return self

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        # "staging" gets production-like behaviour (docs hidden, security headers)
        # but skips https-CORS enforcement so the local prod-like compose works.
        return self.APP_ENV.lower() in ("production", "staging")

    @property
    def normalized_database_url(self) -> str:
        return _normalize_postgres_url(self.DATABASE_URL)

    @property
    def normalized_test_database_url(self) -> str:
        return _normalize_postgres_url(self.TEST_DATABASE_URL)


settings = Settings()
