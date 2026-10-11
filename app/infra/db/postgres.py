import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = structlog.get_logger()


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


async def init_postgresql() -> None:
    """Initialize PostgreSQL connection and create tables with retry logic."""
    global _engine, _session_factory

    settings = get_settings()
    database_url = settings.database_url

    if not database_url:
        logger.warning("DATABASE_URL not set, skipping database initialization")
        return

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Remove asyncpg-incompatible query parameters (like sslmode from NeonDB)
    if "?" in database_url:
        database_url = database_url.split("?")[0]

    # NeonDB requires sslmode=require, asyncpg uses ssl=True
    _engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"ssl": True} if "neon.tech" in database_url else {},
        pool_pre_ping=True,
        pool_recycle=300,
    )

    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

    # Create tables with retries for startup races / availability
    max_retries = 5
    retry_delay = 2
    for attempt in range(max_retries):
        try:
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("PostgreSQL initialized successfully")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Database initialization failed, retrying...",
                    attempt=attempt + 1,
                    error=str(e),
                    next_retry_in=retry_delay,
                )
                import asyncio

                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(
                    "Failed to initialize PostgreSQL after multiple attempts", error=str(e)
                )
                # Don't raise here, allow the app to start but API calls will fail
                # This prevents the whole service from crashing immediately if DB is down


async def close_postgresql() -> None:
    """Close PostgreSQL connection."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None


def get_session() -> AsyncSession:
    """Get a database session."""
    if not _session_factory:
        raise RuntimeError("PostgreSQL not initialized")
    return _session_factory()
