"""Общие фикстуры для тестов: in-memory SQLite-сессии под ORM.

Для unit-тестов нормализации БД не нужна вовсе. Для repository/orchestrator
используем aiosqlite, чтобы не требовать Postgres. Postgres-специфику
(ARRAY/JSONB/gen_random_uuid) подменяем на совместимые типы в conftest.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def sessionmaker():
    """Async sessionmaker на in-memory SQLite с созданной схемой ORM.

    SQLite не знает ARRAY/JSONB/UUID/pg_insert.on_conflict с xmax, поэтому этот
    fixture годится для orchestrator-теста с моками; репозиторный upsert,
    завязанный на Postgres, тестируется отдельно через свой движок.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # gen_random_uuid() недоступен в SQLite — генерируем id на стороне Python.
    from find_engine.storage import orm

    @event.listens_for(orm.ItemORM, "before_insert")
    def _item_id(mapper, connection, target):  # noqa: ANN001
        if target.id is None:
            target.id = uuid.uuid4()

    @event.listens_for(orm.JobORM, "before_insert")
    def _job_id(mapper, connection, target):  # noqa: ANN001
        if target.id is None:
            target.id = uuid.uuid4()

    @event.listens_for(orm.RawRecordORM, "before_insert")
    def _raw_id(mapper, connection, target):  # noqa: ANN001
        if target.id is None:
            target.id = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.run_sync(orm.Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
