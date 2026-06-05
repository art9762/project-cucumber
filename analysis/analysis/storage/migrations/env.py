"""Alembic env (анализ) — async, СВОЯ история.

target_metadata = только Base анализа (analysis_runs/categories/item_analysis).
Таблицы движка (ReadBase) НЕ включаем — ими владеют миграции движка в той же БД.
URL берём из analysis-DSN.

История анализа живёт в той же БД, что и движок, поэтому ведём её в ОТДЕЛЬНОЙ
version-таблице (``alembic_version_analysis``) — иначе ревизии двух независимых
историй сталкиваются в общей ``alembic_version``.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from analysis.config import get_settings
from analysis.storage.orm import Base

config = context.config
target_metadata = Base.metadata

# Отдельная version-таблица, чтобы не пересекаться с историей движка в общей БД.
_VERSION_TABLE = "alembic_version_analysis"


def _url() -> str:
    return get_settings().db_url_analysis


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
