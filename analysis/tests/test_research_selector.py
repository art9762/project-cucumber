"""Тесты селектора item'ов для ресёрча (без Postgres, без сети).

Используется общая фикстура ``analysis_sessionmaker`` из conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analysis.research.selector import select_unresearched_items
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM, ItemResearchORM


def _item(external_id: str, fetched_at: datetime | None = None) -> ItemReadORM:
    """Фабрика тестового ItemReadORM."""
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=fetched_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _item_analysis(item: ItemReadORM, coefficient: float = 0.5) -> ItemAnalysisORM:
    """Фабрика ItemAnalysisORM с заданным coefficient."""
    return ItemAnalysisORM(item_id=item.id, coefficient=coefficient)


@pytest.mark.asyncio
async def test_item_without_research_is_selected(analysis_sessionmaker) -> None:
    """Item с item_analysis, но без item_research попадает в выборку."""
    async with analysis_sessionmaker() as session:
        item = _item("sel1")
        session.add(item)
        await session.flush()
        session.add(_item_analysis(item, coefficient=0.6))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100)

    assert len(result) == 1
    assert result[0][0].external_id == "sel1"


@pytest.mark.asyncio
async def test_item_with_research_is_excluded(analysis_sessionmaker) -> None:
    """Item с существующей строкой item_research не попадает в выборку."""
    async with analysis_sessionmaker() as session:
        item = _item("sel2")
        session.add(item)
        await session.flush()
        session.add(_item_analysis(item, coefficient=0.6))
        await session.flush()
        session.add(ItemResearchORM(item_id=item.id, summary="done", sources=[]))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100)

    ids = [r[0].external_id for r in result]
    assert "sel2" not in ids


@pytest.mark.asyncio
async def test_min_coefficient_filters_weak_items(analysis_sessionmaker) -> None:
    """min_coefficient отсекает item'ы с coefficient ниже порога."""
    async with analysis_sessionmaker() as session:
        item_strong = _item("sel3a")
        item_weak = _item("sel3b")
        session.add_all([item_strong, item_weak])
        await session.flush()
        session.add(_item_analysis(item_strong, coefficient=0.75))
        session.add(_item_analysis(item_weak, coefficient=0.3))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100, min_coefficient=0.5)

    ids = [r[0].external_id for r in result]
    assert "sel3a" in ids
    assert "sel3b" not in ids


@pytest.mark.asyncio
async def test_order_by_coefficient_desc(analysis_sessionmaker) -> None:
    """Item'ы возвращаются по coefficient убыванию."""
    async with analysis_sessionmaker() as session:
        item_low = _item("sel4a")
        item_mid = _item("sel4b")
        item_high = _item("sel4c")
        session.add_all([item_low, item_mid, item_high])
        await session.flush()
        session.add(_item_analysis(item_low, coefficient=0.2))
        session.add(_item_analysis(item_mid, coefficient=0.6))
        session.add(_item_analysis(item_high, coefficient=0.9))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100)

    ext_ids = [r[0].external_id for r in result]
    assert ext_ids.index("sel4c") < ext_ids.index("sel4b")
    assert ext_ids.index("sel4b") < ext_ids.index("sel4a")


@pytest.mark.asyncio
async def test_min_tier_maps_to_coefficient_floor(analysis_sessionmaker) -> None:
    """min_tier='A' отсекает item'ы с coefficient < 0.65."""
    async with analysis_sessionmaker() as session:
        item_a = _item("sel5a")
        item_b = _item("sel5b")
        session.add_all([item_a, item_b])
        await session.flush()
        session.add(_item_analysis(item_a, coefficient=0.7))   # тир A (>=0.65)
        session.add(_item_analysis(item_b, coefficient=0.55))  # тир B (<0.65)
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100, min_tier="A")

    ids = [r[0].external_id for r in result]
    assert "sel5a" in ids
    assert "sel5b" not in ids


@pytest.mark.asyncio
async def test_no_item_analysis_not_selected(analysis_sessionmaker) -> None:
    """Item без строки item_analysis не попадает в выборку."""
    async with analysis_sessionmaker() as session:
        item = _item("sel6")
        session.add(item)
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=100)

    ids = [r[0].external_id for r in result]
    assert "sel6" not in ids


@pytest.mark.asyncio
async def test_limit_caps_result(analysis_sessionmaker) -> None:
    """limit=1 возвращает не более 1 item."""
    async with analysis_sessionmaker() as session:
        items = [_item(f"sel7-{i}") for i in range(5)]
        session.add_all(items)
        await session.flush()
        for item in items:
            session.add(_item_analysis(item, coefficient=0.5))
        await session.commit()

    async with analysis_sessionmaker() as session:
        result = await select_unresearched_items(session, limit=1)

    assert len(result) == 1
