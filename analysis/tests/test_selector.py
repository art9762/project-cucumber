"""Тесты селектора «новых» items (без Postgres, без сети).

Используется общая фикстура ``analysis_sessionmaker`` из conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analysis.storage.orm import ItemAnalysisORM, ItemReadORM
from analysis.storage.selector import select_new_items


def _dt(hour: int) -> datetime:
    """Хелпер: UTC datetime для заданного часа."""
    return datetime(2024, 1, 1, hour, 0, 0, tzinfo=timezone.utc)


def _item(source: str = "test", external_id: str = "x", fetched_at: datetime | None = None) -> ItemReadORM:
    """Фабрика тестового ItemReadORM с минимально необходимыми полями."""
    return ItemReadORM(
        source=source,
        external_id=external_id,
        title="Title",
        url="https://example.com",
        tags=[],
        fetched_at=fetched_at,
    )


@pytest.mark.asyncio
async def test_all_new_when_none_analyzed(analysis_sessionmaker) -> None:
    """3 items без записей в item_analysis → возвращает все 3."""
    async with analysis_sessionmaker() as session:
        items = [
            _item("s", "a", _dt(1)),
            _item("s", "b", _dt(2)),
            _item("s", "c", _dt(3)),
        ]
        session.add_all(items)
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_new_items(session, limit=100)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_analyzed_item_excluded(analysis_sessionmaker) -> None:
    """1 из 3 items помечен как проанализированный → возвращает 2."""
    async with analysis_sessionmaker() as session:
        items = [
            _item("s", "a", _dt(1)),
            _item("s", "b", _dt(2)),
            _item("s", "c", _dt(3)),
        ]
        session.add_all(items)
        await session.flush()

        analyzed_id = items[0].id
        session.add(ItemAnalysisORM(item_id=analyzed_id))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_new_items(session, limit=100)

    assert len(result) == 2
    result_ids = {r.id for r in result}
    assert analyzed_id not in result_ids


@pytest.mark.asyncio
async def test_limit_caps_result(analysis_sessionmaker) -> None:
    """limit=1 возвращает не более 1 item из 3."""
    async with analysis_sessionmaker() as session:
        items = [
            _item("s", "a", _dt(1)),
            _item("s", "b", _dt(2)),
            _item("s", "c", _dt(3)),
        ]
        session.add_all(items)
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_new_items(session, limit=1)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_ordering_by_fetched_at(analysis_sessionmaker) -> None:
    """Items возвращаются в порядке fetched_at ASC."""
    async with analysis_sessionmaker() as session:
        # Добавляем в обратном порядке fetched_at
        items = [
            _item("s", "c", _dt(3)),
            _item("s", "a", _dt(1)),
            _item("s", "b", _dt(2)),
        ]
        session.add_all(items)
        await session.flush()

        # Запоминаем id в порядке fetched_at (1,2,3)
        by_time = sorted(items, key=lambda i: i.fetched_at)
        expected_order = [i.id for i in by_time]
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_new_items(session, limit=100)

    assert [r.id for r in result] == expected_order
