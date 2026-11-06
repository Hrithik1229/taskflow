from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def lock_project_tasks(session: AsyncSession, project_id: UUID) -> None:
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(f"taskflow:{project_id}", 0)
            )
        )
    )
