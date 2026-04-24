"""Database base configuration for praisonai-platform."""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Global engine instance
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Get (and lazily create) the cached async database engine.

    If ``database_url`` is provided and no engine is cached yet, it overrides
    the ``DATABASE_URL`` env var / in-memory default. To switch URLs after an
    engine has already been created, call ``reset_engine()`` first.
    """
    global _engine
    if _engine is None:
        if database_url is None:
            # Default to in-memory SQLite for testing
            database_url = os.environ.get(
                "DATABASE_URL",
                "sqlite+aiosqlite:///:memory:",
            )
        _engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        )
    return _engine


async def reset_engine() -> None:
    """Reset the global engine (for testing).

    Disposes the existing async engine (if any) before clearing
    cached references so connection pools don't leak across tests.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Initialize the database (create all tables)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)