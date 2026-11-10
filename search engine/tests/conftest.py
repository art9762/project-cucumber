"""Общие фикстуры для тестов: in-memory SQLite-сессии под ORM.

Для unit-тестов нормализации БД не нужна вовсе. Для repository/orchestrator
используем aiosqlite, чтобы не требовать Postgres. Postgres-специфику
(ARRAY/JSONB/gen_random_uuid) подменяем на совместимые типы в conftest.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import event, text
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
    def _item_id(mapper, connection, target):
        if target.id is None:
            target.id = uuid.uuid4()

    @event.listens_for(orm.JobORM, "before_insert")
    def _job_id(mapper, connection, target):
        if target.id is None:
            target.id = uuid.uuid4()

    @event.listens_for(orm.RawRecordORM, "before_insert")
    def _raw_id(mapper, connection, target):
        if target.id is None:
            target.id = uuid.uuid4()

    async with engine.begin() as conn:
        await conn.run_sync(orm.Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_sessionmaker():
    """Use an explicitly opted-in test DB and a fresh schema for each test.

    Never fall back to DB_URL/.env: those may point at the application database.
    An explicit but unavailable TEST_DB_URL fails the test instead of hiding a
    broken integration environment behind a skip.
    """
    from find_engine.storage.orm import Base

    url = os.environ.get("TEST_DB_URL")
    if not url:
        pytest.skip("Set TEST_DB_URL to a disposable PostgreSQL database for integration tests")
    if not url.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DB_URL must use the postgresql+asyncpg driver")

    schema = f"cucumber_test_{uuid.uuid4().hex}"
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema}}
    )
    created = False
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        try:
            if created:
                async with engine.begin() as conn:
                    await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            await engine.dispose()
