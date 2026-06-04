"""Подключение к Postgres: раздельные async engine'ы под read и analysis DSN.

- read-engine — для SELECT по таблицам движка (read-only контракт);
- analysis-engine — для своих таблиц анализа.

По умолчанию оба DSN совпадают (см. config), но разнесены, чтобы в Фазе 6
дать read-роли только SELECT, не трогая код.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from analysis.config import get_settings

_read_engine: AsyncEngine | None = None
_analysis_engine: AsyncEngine | None = None
_read_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_analysis_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_read_engine() -> AsyncEngine:
    global _read_engine
    if _read_engine is None:
        _read_engine = create_async_engine(
            get_settings().read_url_effective, pool_pre_ping=True
        )
    return _read_engine


def get_analysis_engine() -> AsyncEngine:
    global _analysis_engine
    if _analysis_engine is None:
        _analysis_engine = create_async_engine(
            get_settings().db_url_analysis, pool_pre_ping=True
        )
    return _analysis_engine


def get_read_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _read_sessionmaker
    if _read_sessionmaker is None:
        _read_sessionmaker = async_sessionmaker(get_read_engine(), expire_on_commit=False)
    return _read_sessionmaker


def get_analysis_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _analysis_sessionmaker
    if _analysis_sessionmaker is None:
        _analysis_sessionmaker = async_sessionmaker(
            get_analysis_engine(), expire_on_commit=False
        )
    return _analysis_sessionmaker


async def get_read_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: read-сессия на запрос."""
    async with get_read_sessionmaker()() as session:
        yield session


async def get_analysis_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: analysis-сессия на запрос."""
    async with get_analysis_sessionmaker()() as session:
        yield session
