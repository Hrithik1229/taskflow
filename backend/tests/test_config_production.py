"""
tests/test_config_production.py

Unit tests for:
- DATABASE_URL normalization (all realistic provider URL formats)
- Production secret validation (placeholder rejection, minimum length)
- Production CORS https enforcement
"""

import pytest
from pydantic import ValidationError

from app.config import Settings, _normalize_postgres_url

# ---------------------------------------------------------------------------
# _normalize_postgres_url — isolated function tests
# ---------------------------------------------------------------------------


class TestNormalizePostgresUrl:
    """Tests use fake credentials — no real database is contacted."""

    def test_postgres_scheme_becomes_asyncpg(self):
        url = "postgres://user:pass@localhost:5432/mydb"
        result = _normalize_postgres_url(url)
        assert result.startswith("postgresql+asyncpg://")

    def test_postgresql_scheme_becomes_asyncpg(self):
        url = "postgresql://user:pass@localhost/mydb"
        result = _normalize_postgres_url(url)
        assert result.startswith("postgresql+asyncpg://")

    def test_already_asyncpg_scheme_untouched(self):
        url = "postgresql+asyncpg://user:pass@host/db?ssl=require"
        assert _normalize_postgres_url(url) == url

    def test_sslmode_require_mapped_to_ssl(self):
        """Neon and other managed providers provide sslmode=require."""
        url = (
            "postgres://user:pass@ep-cool-123.us-east-2.aws.neon.tech/db"
            "?sslmode=require"
        )
        result = _normalize_postgres_url(url)
        assert "ssl=require" in result
        assert "sslmode" not in result

    def test_channel_binding_stripped(self):
        """channel_binding is a libpq param; asyncpg raises on it."""
        url = (
            "postgres://user:pass@ep-cool-123.us-east-2.aws.neon.tech/db"
            "?sslmode=require&channel_binding=require"
        )
        result = _normalize_postgres_url(url)
        assert "channel_binding" not in result
        assert "ssl=require" in result

    def test_sslmode_verify_full_mapped(self):
        url = "postgresql://user:pass@db.example.com/prod?sslmode=verify-full"
        result = _normalize_postgres_url(url)
        assert "ssl=verify-full" in result
        assert "sslmode" not in result

    def test_neon_full_url(self):
        """Realistic Neon free-tier connection string."""
        url = (
            "postgresql://neondb_owner:AbCdEfGh123@"
            "ep-cool-darkness-a1b2c3d4.us-east-2.aws.neon.tech"
            "/neondb?sslmode=require&channel_binding=require"
        )
        result = _normalize_postgres_url(url)
        assert result.startswith("postgresql+asyncpg://")
        assert "ssl=require" in result
        assert "channel_binding" not in result
        assert "sslmode" not in result

    def test_local_no_ssl(self):
        """Local Docker Postgres: no query params, no SSL."""
        url = "postgresql://taskflow_dev:dev_only@localhost:5432/taskflow_dev"
        result = _normalize_postgres_url(url)
        assert (
            result
            == "postgresql+asyncpg://taskflow_dev:dev_only@localhost:5432/taskflow_dev"
        )

    def test_empty_string_passthrough(self):
        assert _normalize_postgres_url("") == ""

    def test_non_postgres_url_passthrough(self):
        """SQLite or other URLs must not be modified."""
        url = "sqlite+aiosqlite:///./test.db"
        assert _normalize_postgres_url(url) == url

    def test_credentials_preserved(self):
        url = "postgres://my_user:s3cr3t%40word@db.host.com:5432/app_db?sslmode=require"
        result = _normalize_postgres_url(url)
        assert "my_user" in result
        # Password preserved (URL-encoded @ remains)
        assert "s3cr3t" in result

    def test_application_name_stripped(self):
        """application_name is not supported by asyncpg as a query param."""
        url = "postgresql://u:p@host/db?application_name=taskflow"
        result = _normalize_postgres_url(url)
        assert "application_name" not in result

    def test_multiple_unknown_params_stripped(self):
        url = (
            "postgresql://u:p@host/db"
            "?sslmode=require&channel_binding=require&application_name=app"
        )
        result = _normalize_postgres_url(url)
        assert "ssl=require" in result
        assert "channel_binding" not in result
        assert "application_name" not in result


# ---------------------------------------------------------------------------
# Settings — production validation
# ---------------------------------------------------------------------------


class TestProductionSettings:
    """
    These tests instantiate Settings directly with controlled values to avoid
    reading from .env files.  APP_ENV=test bypasses the production guard for
    most tests; APP_ENV=production tests the production path explicitly.
    """

    def _prod_settings(self, **overrides) -> dict:
        """Return a valid production-ready Settings kwargs dict."""
        base = dict(
            APP_ENV="production",
            APP_SECRET_KEY="a" * 32,  # 32 chars, no placeholder
            JWT_SECRET_KEY="b" * 32,
            DATABASE_URL="postgresql+asyncpg://u:p@host/db",
            CORS_ORIGINS="https://app.example.com",
        )
        base.update(overrides)
        return base

    def test_valid_production_settings(self):
        s = Settings(**self._prod_settings())
        assert s.is_production is True

    def test_placeholder_app_secret_rejected(self):
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(
                **self._prod_settings(
                    APP_SECRET_KEY="replace-with-a-long-random-development-secret"
                )
            )

    def test_placeholder_jwt_secret_rejected(self):
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(
                **self._prod_settings(
                    JWT_SECRET_KEY="replace-with-a-different-long-random-development-secret"
                )
            )

    def test_too_short_secret_rejected(self):
        # Use short string with no placeholder keywords so only length check fires
        with pytest.raises(ValidationError, match="too short"):
            Settings(**self._prod_settings(APP_SECRET_KEY="Z9q2" * 5))

    def test_production_http_cors_rejected(self):
        with pytest.raises(ValidationError, match="must use https"):
            Settings(**self._prod_settings(CORS_ORIGINS="http://app.example.com"))

    def test_production_wildcard_cors_rejected(self):
        with pytest.raises(ValidationError, match="explicit origins"):
            Settings(**self._prod_settings(CORS_ORIGINS="*"))

    def test_missing_secrets_rejected_in_development(self):
        with pytest.raises(ValidationError, match="Missing required secret"):
            Settings(APP_ENV="development", APP_SECRET_KEY=None, JWT_SECRET_KEY=None)

    def test_secrets_not_required_in_test(self):
        """APP_ENV=test must start without secrets (used by test suite)."""
        s = Settings(APP_ENV="test", DATABASE_URL="postgresql+asyncpg://u:p@h/d")
        assert s.is_production is False

    def test_normalized_url_in_settings(self):
        s = Settings(
            APP_ENV="test",
            DATABASE_URL="postgres://u:p@host/db?sslmode=require&channel_binding=require",
        )
        assert s.normalized_database_url.startswith("postgresql+asyncpg://")
        assert "ssl=require" in s.normalized_database_url
        assert "channel_binding" not in s.normalized_database_url

    def test_cors_list_strips_whitespace(self):
        s = Settings(
            APP_ENV="test",
            CORS_ORIGINS=" https://app.example, https://admin.example ",
        )
        assert s.cors_origins_list == ["https://app.example", "https://admin.example"]

    def test_pool_settings_defaults(self):
        s = Settings(APP_ENV="test")
        assert s.DB_POOL_SIZE == 3
        assert s.DB_MAX_OVERFLOW == 2
        assert s.DB_POOL_RECYCLE == 300
