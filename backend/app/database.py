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

# ---------------------------------------------------------------------------
# Connection pool — tuned for managed Postgres with limited connections
# (see Settings docstring for rationale on each parameter).
#
# pool_pre_ping=True  — asyncpg validates each connection before use;
#   avoids "connection was closed in the middle of operation" after
#   Neon scale-to-zero or Render cold-start restarts the database process.
#
# pool_recycle=300    — recycle connections every 5 min; prevents the pool
#   from holding stale TCP connections that the managed DB has already
#   silently dropped on its end.
#
# connect_args["server_settings"]["timezone"] = "UTC" — Postgres session
#   timezone set at connect time so all datetime comparisons are unambiguous
#   regardless of server OS timezone.
# ---------------------------------------------------------------------------
engine = create_async_engine(
    settings.normalized_database_url,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
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
