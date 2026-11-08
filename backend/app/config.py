from __future__ import annotations

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def reject_wildcard_cors(cls, origins: str) -> str:
        if "*" in [origin.strip() for origin in origins.split(",")]:
            raise ValueError(
                "CORS_ORIGINS must list explicit origins; '*' is not allowed"
            )
        return origins

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]

    @model_validator(mode="after")
    def require_secrets_outside_tests(self) -> Settings:
        if self.APP_ENV.lower() != "test":
            missing = [
                name
                for name, value in (
                    ("APP_SECRET_KEY", self.APP_SECRET_KEY),
                    ("JWT_SECRET_KEY", self.JWT_SECRET_KEY),
                )
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(
                    f"Missing required secret(s): {joined}. "
                    "Set them in the environment or backend/.env."
                )
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def normalized_database_url(self) -> str:
        return self._normalize_postgres_url(self.DATABASE_URL)

    @property
    def normalized_test_database_url(self) -> str:
        return self._normalize_postgres_url(self.TEST_DATABASE_URL)

    @staticmethod
    def _normalize_postgres_url(url: str) -> str:
        if url.startswith(("postgres://", "postgresql://")):
            return url.replace("postgres://", "postgresql+asyncpg://", 1).replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        return url


settings = Settings()
