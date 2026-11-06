import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_parse_origins_and_normalize_database_urls() -> None:
    config = Settings(
        APP_ENV="test",
        CORS_ORIGINS=" https://app.example, https://admin.example ",
        DATABASE_URL="postgres://user:password@localhost/taskflow",
        TEST_DATABASE_URL="postgresql://user:password@localhost/taskflow_test",
    )

    assert config.cors_origins_list == [
        "https://app.example",
        "https://admin.example",
    ]
    assert (
        config.normalized_database_url
        == "postgresql+asyncpg://user:password@localhost/taskflow"
    )
    assert (
        config.normalized_test_database_url
        == "postgresql+asyncpg://user:password@localhost/taskflow_test"
    )


def test_settings_reject_wildcard_cors() -> None:
    with pytest.raises(ValidationError, match="explicit origins"):
        Settings(APP_ENV="test", CORS_ORIGINS="*")


def test_settings_require_secrets_outside_tests() -> None:
    with pytest.raises(ValidationError, match="Missing required secret"):
        Settings(APP_ENV="development", APP_SECRET_KEY=None, JWT_SECRET_KEY=None)
