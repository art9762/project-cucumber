"""Общие фикстуры тестов.

Паттерн движка: unit-тесты не требуют ни сети, ни Postgres. Для БД-логики
(селектор «новых items») используем in-memory SQLite на одном движке, где
созданы и таблицы движка (`items`, через ReadBase), и свои (`item_analysis`,
через Base) — тогда FK item_analysis.item_id → items.id резолвится.

Postgres-специфику (UUID server_default `gen_random_uuid()`, `now()`) SQLite не
знает, поэтому id и временные метки проставляем на стороне Python через
before_insert — как сделано для repository-тестов движка.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def analysis_sessionmaker():
    """Async sessionmaker на in-memory SQLite со схемой items + таблиц анализа."""
    from analysis.storage import orm

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # server_default'ы Postgres недоступны в SQLite — заполняем в Python.
    @event.listens_for(orm.ItemReadORM, "before_insert")
    def _item_defaults(mapper, connection, target):  # noqa: ANN001
        if target.id is None:
            target.id = uuid.uuid4()

    for model in (
        orm.AnalysisRunORM,
        orm.CategoryORM,
        orm.ItemAnalysisORM,
        orm.ItemResearchORM,
        orm.ItemEmbeddingORM,
        orm.UserORM,
        orm.SessionORM,
    ):

        @event.listens_for(model, "before_insert")
        def _id_default(mapper, connection, target):  # noqa: ANN001
            if getattr(target, "id", None) is None:
                target.id = uuid.uuid4()

    @event.listens_for(orm.UserORM, "before_insert")
    def _user_defaults(mapper, connection, target):  # noqa: ANN001
        if target.role is None:
            target.role = "viewer"
        if target.is_active is None:
            target.is_active = True
        if target.created_at is None:
            target.created_at = _utcnow()

    @event.listens_for(orm.SessionORM, "before_insert")
    def _session_created(mapper, connection, target):  # noqa: ANN001
        if target.created_at is None:
            target.created_at = _utcnow()

    @event.listens_for(orm.ItemResearchORM, "before_insert")
    def _research_at(mapper, connection, target):  # noqa: ANN001
        if target.researched_at is None:
            target.researched_at = _utcnow()

    @event.listens_for(orm.ItemEmbeddingORM, "before_insert")
    def _embedded_at(mapper, connection, target):  # noqa: ANN001
        if target.embedded_at is None:
            target.embedded_at = _utcnow()

    @event.listens_for(orm.CategoryORM, "before_insert")
    def _cat_created(mapper, connection, target):  # noqa: ANN001
        if target.created_at is None:
            target.created_at = _utcnow()

    @event.listens_for(orm.ItemAnalysisORM, "before_insert")
    def _ia_analyzed(mapper, connection, target):  # noqa: ANN001
        if target.analyzed_at is None:
            target.analyzed_at = _utcnow()

    async with engine.begin() as conn:
        await conn.run_sync(orm.ReadBase.metadata.create_all)
        await conn.run_sync(orm.Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
