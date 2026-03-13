# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Database Engine & Session Factory
# SQLAlchemy + GeoAlchemy2 (PostGIS) / SQLite (dev mode)
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


# ── Detect dev mode (SQLite) vs production (PostgreSQL) ──────
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    # SQLite async via aiosqlite
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
    sync_engine = create_engine(
        settings.DATABASE_SYNC_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL with connection pooling
    async_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )
    sync_engine = create_engine(
        settings.DATABASE_SYNC_URL,
        echo=settings.DEBUG,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
    )


AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


# ── Declarative Base ─────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Dependency for FastAPI ────────────────────────────────────
async def get_db() -> AsyncSession:
    """Yields an async session — auto-closed on exit."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Session:
    """Returns a sync session for Celery/Airflow tasks."""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

