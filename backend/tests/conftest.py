import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command

os.environ["APP_ENV"] = "test"

from app.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[1]


def get_test_database_url() -> str | None:
    value = Settings().normalized_test_database_url
    return value or None


async def postgres_is_reachable(url: str) -> bool:
    parsed_url = make_url(url)
    if parsed_url.host is None:
        return False

    try:
        engine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"timezone": "UTC"}},
        )
        async with engine.connect() as conn:
            await conn.execute(select(1))
        await engine.dispose()
        return True
    except Exception:
        return False


def run_alembic(url: str, operation: str, revision: str | None = None) -> None:
    previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        getattr(command, operation)(config, revision) if revision else getattr(
            command, operation
        )(config)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    url = get_test_database_url()
    if not url:
        pytest.skip(
            "Set TEST_DATABASE_URL to a dedicated PostgreSQL database to run "
            "database integration tests."
        )
    if not await postgres_is_reachable(url):
        pytest.skip(
            "The PostgreSQL server configured by TEST_DATABASE_URL is not "
            "reachable; database integration tests were not run."
        )

    await asyncio.to_thread(run_alembic, url, "upgrade", "head")
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args={"server_settings": {"timezone": "UTC"}},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        outer_transaction = await connection.begin()
        factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as test_session:
            try:
                yield test_session
            finally:
                if outer_transaction.is_active:
                    await outer_transaction.rollback()


@pytest.fixture
def migration_runner() -> Any:
    return run_alembic
