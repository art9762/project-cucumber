"""Upsert/дедуп репозитория. Требует реального Postgres (ON CONFLICT + xmax).

Нужен TEST_DB_URL отдельной тестовой БД; каждый тест использует свою схему.
Без TEST_DB_URL модуль пропускается, недоступная явно заданная БД — ошибка.
"""

from __future__ import annotations

from datetime import UTC

from find_engine.core.models import Item
from find_engine.storage.repository import Repository


def _item(ext: str, title: str, score: int) -> Item:
    return Item(
        source="test", external_id=ext, title=title,
        url=f"http://x/{ext}", score=score, tags=["a", "b"],
    )


async def test_upsert_inserts_then_dedups(pg_sessionmaker):
    async with pg_sessionmaker() as session:
        repo = Repository(session)

        _, inserted = await repo.upsert_item(_item("1", "first", 10), payload={"v": 1})
        assert inserted is True

        # тот же (source, external_id) → update, не новая запись
        _, inserted2 = await repo.upsert_item(_item("1", "updated", 20), payload={"v": 2})
        assert inserted2 is False
        await session.commit()

        row = await repo.get_item("test", "1")
        assert row is not None
        assert row.title == "updated"
        assert row.score == 20


async def test_watermark_from_last_success(pg_sessionmaker):
    from datetime import datetime

    from find_engine.core.models import JobState, JobStats

    async with pg_sessionmaker() as session:
        repo = Repository(session)
        job = await repo.create_job("test", since=None)
        ts = datetime(2026, 6, 4, tzinfo=UTC)
        await repo.update_job(
            job.id, status=JobState.success, stats=JobStats(), finished_at=ts
        )
        await session.commit()

        wm = await repo.last_successful_watermark("test")
        assert wm == ts
