from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

if not settings.normalized_database_url:
    raise RuntimeError(
        "DATABASE_URL is required to initialize the database. "
        "Set it in the environment or backend/.env."
    )

engine = create_async_engine(
    settings.normalized_database_url,
    pool_pre_ping=True,
    connect_args={"server_settings": {"timezone": "UTC"}},
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield one request-scoped session; callers explicitly commit successful writes."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
