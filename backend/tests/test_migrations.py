import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings


@pytest.mark.asyncio
async def test_migrations_can_downgrade_upgrade_and_have_no_drift(
    test_engine: AsyncEngine,
    migration_runner: Callable[..., None],
) -> None:
    database_url = Settings().normalized_test_database_url
    assert database_url

    await asyncio.to_thread(
        migration_runner,
        database_url,
        "downgrade",
        "0001_initial_schema",
    )
    owner_id = uuid4()
    project_id = uuid4()
    task_id = uuid4()
    first_move_id = uuid4()
    latest_move_id = uuid4()
    first_move_at = datetime.now(UTC) - timedelta(days=2)
    latest_move_at = datetime.now(UTC) - timedelta(days=1)
    async with test_engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO users (id, username, email, password_hash)
                VALUES (:id, 'migration-user', :email, 'not-used')
                """
            ),
            {"id": owner_id, "email": f"{owner_id}@example.com"},
        )
        await connection.execute(
            text(
                """
                INSERT INTO projects (id, name, owner_id)
                VALUES (:id, 'Migration project', :owner_id)
                """
            ),
            {"id": project_id, "owner_id": owner_id},
        )
        await connection.execute(
            text(
                """
                INSERT INTO tasks (
                    id, project_id, title, created_by, status, position, version
                )
                VALUES (
                    :id, :project_id, 'Legacy moved task', :owner_id,
                    'completed', 0, 3
                )
                """
            ),
            {"id": task_id, "project_id": project_id, "owner_id": owner_id},
        )
        for log_id, created_at in (
            (first_move_id, first_move_at),
            (latest_move_id, latest_move_at),
        ):
            await connection.execute(
                text(
                    """
                    INSERT INTO activity_logs (
                        id, project_id, actor_id, action, entity_type, entity_id,
                        details, created_at
                    )
                    VALUES (
                        :id, :project_id, :actor_id, 'task.moved', 'task', :task_id,
                        CAST('{}' AS jsonb), :created_at
                    )
                    """
                ),
                {
                    "id": log_id,
                    "project_id": project_id,
                    "actor_id": owner_id,
                    "task_id": task_id,
                    "created_at": created_at,
                },
            )

    await asyncio.to_thread(migration_runner, database_url, "upgrade", "head")
    async with test_engine.connect() as connection:
        backfilled = (
            await connection.execute(
                text(
                    """
                    SELECT status_changed_by, status_changed_at, completed_by
                    FROM tasks
                    WHERE id = :task_id
                    """
                ),
                {"task_id": task_id},
            )
        ).one()
    assert backfilled.status_changed_by == owner_id
    assert backfilled.status_changed_at == latest_move_at
    assert backfilled.completed_by is None

    await asyncio.to_thread(migration_runner, database_url, "downgrade", "base")
    await asyncio.to_thread(migration_runner, database_url, "upgrade", "head")
    await asyncio.to_thread(migration_runner, database_url, "check")
