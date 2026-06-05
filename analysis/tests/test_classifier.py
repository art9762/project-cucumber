"""Тесты оркестратора классификации (без Postgres, без сети).

Использует общую фикстуру ``analysis_sessionmaker`` из conftest.py для обоих
sessionmaker'ов: в тестовой SQLite обе схемы живут на одном движке.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from analysis.classify.classifier import run_classification
from analysis.storage.orm import AnalysisRunORM, CategoryORM, ItemAnalysisORM, ItemReadORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _item(external_id: str = "x") -> ItemReadORM:
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _category(slug: str, title: str, approved: bool = True) -> CategoryORM:
    return CategoryORM(slug=slug, title=title, approved=approved)


def _trinity(response: str) -> AsyncMock:
    """Создать фиктивный TrinityClient с одним ответом."""
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value=response)
    return mock


def _ai_json(suggested: dict | None = None) -> str:
    payload: dict = {"category": "ai", "confidence": 0.9, "suggested_subcategory": suggested}
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_classifies_item(analysis_sessionmaker) -> None:
    """item получает строку item_analysis с category_id == ai и model_used."""
    async with analysis_sessionmaker() as session:
        cat = _category("ai", "Искусственный интеллект")
        item = _item("a1")
        session.add(cat)
        session.add(item)
        await session.commit()
        cat_id = cat.id
        item_id = item.id

    trinity = _trinity(_ai_json())
    stats = await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    assert stats.seen == 1
    assert stats.classified == 1
    assert stats.failed == 0

    async with analysis_sessionmaker() as session:
        from sqlalchemy import select
        result = await session.execute(select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item_id))
        ia = result.scalars().first()
        assert ia is not None
        assert ia.category_id == cat_id
        assert ia.model_used == "test-model"


@pytest.mark.asyncio
async def test_suggestion_creates_unapproved_subcategory(analysis_sessionmaker) -> None:
    """Модель предлагает подкатегорию → узел создаётся с approved=False; item привязан к родителю."""
    async with analysis_sessionmaker() as session:
        cat = _category("ai", "AI")
        item = _item("b1")
        session.add(cat)
        session.add(item)
        await session.commit()
        parent_id = cat.id
        item_id = item.id

    suggestion = {"slug": "llm-agents", "title": "LLM-агенты"}
    trinity = _trinity(_ai_json(suggested=suggestion))
    stats = await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    assert stats.classified == 1
    assert stats.suggested == 1

    async with analysis_sessionmaker() as session:
        from sqlalchemy import select
        # Item привязан к родителю.
        ia_result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item_id)
        )
        ia = ia_result.scalars().first()
        assert ia is not None
        assert ia.category_id == parent_id

        # Подкатегория создана с approved=False.
        sub_result = await session.execute(
            select(CategoryORM).where(CategoryORM.slug == "llm-agents")
        )
        sub = sub_result.scalars().first()
        assert sub is not None
        assert sub.approved is False
        assert sub.parent_id == parent_id


@pytest.mark.asyncio
async def test_unknown_category_falls_back_to_other(analysis_sessionmaker) -> None:
    """Если модель вернула неизвестный slug, item привязывается к 'other'."""
    async with analysis_sessionmaker() as session:
        other_cat = _category("other", "Прочее")
        item = _item("c1")
        session.add(other_cat)
        session.add(item)
        await session.commit()
        other_id = other_cat.id
        item_id = item.id

    response = json.dumps({"category": "totally-unknown-slug", "confidence": 0.5, "suggested_subcategory": None})
    trinity = _trinity(response)
    stats = await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    assert stats.classified == 1
    assert stats.failed == 0

    async with analysis_sessionmaker() as session:
        from sqlalchemy import select
        ia_result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item_id)
        )
        ia = ia_result.scalars().first()
        assert ia is not None
        assert ia.category_id == other_id


@pytest.mark.asyncio
async def test_idempotency_second_run_sees_zero(analysis_sessionmaker) -> None:
    """Второй прогон не трогает уже классифицированный item: stats.seen == 0."""
    async with analysis_sessionmaker() as session:
        cat = _category("ai", "AI")
        item = _item("d1")
        session.add(cat)
        session.add(item)
        await session.commit()

    trinity = _trinity(_ai_json())
    await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    stats2 = await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    assert stats2.seen == 0
    assert stats2.classified == 0


@pytest.mark.asyncio
async def test_per_item_failure_does_not_abort_run(analysis_sessionmaker) -> None:
    """Первый item возвращает невалидный JSON → failed==1; второй классифицируется."""
    async with analysis_sessionmaker() as session:
        cat = _category("ai", "AI")
        # Задаём разные fetched_at, чтобы порядок SELECT был детерминированным.
        item1 = ItemReadORM(
            source="test", external_id="e1", title="Title e1",
            url="https://example.com/e1", tags=[],
            fetched_at=datetime(2024, 1, 1, 1, tzinfo=timezone.utc),
        )
        item2 = ItemReadORM(
            source="test", external_id="e2", title="Title e2",
            url="https://example.com/e2", tags=[],
            fetched_at=datetime(2024, 1, 1, 2, tzinfo=timezone.utc),
        )
        session.add_all([cat, item1, item2])
        await session.commit()
        item2_id = item2.id

    trinity = AsyncMock()
    trinity.complete = AsyncMock(side_effect=["not valid json at all", _ai_json()])

    stats = await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    assert stats.seen == 2
    assert stats.failed == 1
    assert stats.classified == 1
    assert len(stats.errors) == 1

    async with analysis_sessionmaker() as session:
        from sqlalchemy import select
        ia_result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item2_id)
        )
        ia = ia_result.scalars().first()
        assert ia is not None, "Второй item должен быть классифицирован"


@pytest.mark.asyncio
async def test_analysis_run_row_created_and_finalized(analysis_sessionmaker) -> None:
    """После прогона в analysis_runs есть строка kind='classify' со статусом success."""
    async with analysis_sessionmaker() as session:
        cat = _category("ai", "AI")
        item = _item("f1")
        session.add(cat)
        session.add(item)
        await session.commit()

    trinity = _trinity(_ai_json())
    await run_classification(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
    )

    async with analysis_sessionmaker() as session:
        from sqlalchemy import select
        runs_result = await session.execute(
            select(AnalysisRunORM).where(AnalysisRunORM.kind == "classify")
        )
        run = runs_result.scalars().first()
        assert run is not None
        assert run.kind == "classify"
        assert run.status == "success"
        assert run.finished_at is not None
        assert run.started_at is not None
        assert run.stats is not None
        assert run.stats.get("classified") == 1
