"""Тесты оркестратора ресёрча (без Postgres, без сети).

Использует общую фикстуру ``analysis_sessionmaker`` из conftest.py.
TrinityClient мокается — search_complete возвращает (json_text, sources).
build_research_prompt и parse_research заглушаются через monkeypatch.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from analysis.research.models import Competitor, ResearchResult
from analysis.research.researcher import run_research
from analysis.storage.orm import AnalysisRunORM, ItemAnalysisORM, ItemReadORM, ItemResearchORM

# ---------------------------------------------------------------------------
# JSON, соответствующий контракту parse_research (summary, competitors, signals).
# ---------------------------------------------------------------------------
_VALID_JSON = (
    '{"summary": "A great tool for testing.", '
    '"competitors": [{"name": "CompA", "url": "https://compa.io", "note": "main rival"}], '
    '"maturity_signal": 0.6, "potential_signal": 0.7, "confidence": 0.8}'
)
_SOURCES = ["https://src.example.com"]

_STUB_SYSTEM = "system prompt"
_STUB_MESSAGES = [{"role": "user", "content": "research this"}]

_STUB_RESULT = ResearchResult(
    summary="A great tool for testing.",
    competitors=[Competitor(name="CompA", url="https://compa.io", note="main rival")],
    sources=_SOURCES,
    maturity_signal=0.6,
    potential_signal=0.7,
    confidence=0.8,
)


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _item(external_id: str) -> ItemReadORM:
    """Создать тестовый ItemReadORM."""
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _trinity() -> AsyncMock:
    """Создать фиктивный TrinityClient с search_complete → (json, sources)."""
    mock = AsyncMock()
    mock.search_complete = AsyncMock(return_value=(_VALID_JSON, _SOURCES))
    return mock


def _patch_prompt(monkeypatch) -> None:  # noqa: ANN001
    """Заглушить build_research_prompt."""
    monkeypatch.setattr(
        "analysis.research.researcher.build_research_prompt",
        lambda item, category_title=None: (_STUB_SYSTEM, _STUB_MESSAGES),
    )


def _patch_parse_ok(monkeypatch, result: ResearchResult = _STUB_RESULT) -> None:  # noqa: ANN001
    """Заглушить parse_research — всегда возвращает result."""
    monkeypatch.setattr(
        "analysis.research.researcher.parse_research",
        lambda text, sources: result,
    )


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_writes_item_research(analysis_sessionmaker, monkeypatch) -> None:
    """После успешного прогона item_research записан, stats.researched == 1."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        item = _item("res1")
        session.add(item)
        await session.flush()
        session.add(ItemAnalysisORM(item_id=item.id, coefficient=0.7))
        await session.commit()
        item_id = item.id

    trinity = _trinity()
    stats = await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    assert stats.seen == 1
    assert stats.researched == 1
    assert stats.failed == 0
    assert stats.competitors_found == 1

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemResearchORM).where(ItemResearchORM.item_id == item_id)
        )
        row = result.scalars().first()
        assert row is not None
        assert row.summary == "A great tool for testing."
        assert row.model_used == "test-model"
        assert isinstance(row.competitors, list)
        assert len(row.competitors) == 1
        assert row.competitors[0]["name"] == "CompA"
        assert row.sources == _SOURCES


@pytest.mark.asyncio
async def test_idempotency_second_run_sees_zero(analysis_sessionmaker, monkeypatch) -> None:
    """Второй прогон не трогает уже разобранный item: stats.seen == 0."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        item = _item("res2")
        session.add(item)
        await session.flush()
        session.add(ItemAnalysisORM(item_id=item.id, coefficient=0.7))
        await session.commit()

    trinity = _trinity()
    await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    stats2 = await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    assert stats2.seen == 0
    assert stats2.researched == 0


@pytest.mark.asyncio
async def test_per_item_failure_does_not_abort_run(analysis_sessionmaker, monkeypatch) -> None:
    """parse_research бросает на первом item → failed==1, researched==1, прогон не обрывается."""
    _patch_prompt(monkeypatch)

    call_count = 0

    def _parse_side_effect(text: str, sources: list[str]) -> ResearchResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("bad llm response")
        return _STUB_RESULT

    monkeypatch.setattr("analysis.research.researcher.parse_research", _parse_side_effect)

    async with analysis_sessionmaker() as session:
        item1 = _item("res3a")
        item2 = _item("res3b")
        session.add_all([item1, item2])
        await session.flush()
        # item1 gets higher coefficient so it comes first (and will fail)
        session.add(ItemAnalysisORM(item_id=item1.id, coefficient=0.9))
        session.add(ItemAnalysisORM(item_id=item2.id, coefficient=0.5))
        await session.commit()
        item2_id = item2.id

    trinity = _trinity()
    stats = await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    assert stats.seen == 2
    assert stats.failed == 1
    assert stats.researched == 1
    assert len(stats.errors) == 1

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemResearchORM).where(ItemResearchORM.item_id == item2_id)
        )
        row = result.scalars().first()
        assert row is not None, "Второй item должен быть разобран"
        assert row.summary == "A great tool for testing."


@pytest.mark.asyncio
async def test_analysis_runs_row_recorded_kind_research(analysis_sessionmaker, monkeypatch) -> None:
    """После прогона в analysis_runs есть строка kind='research', status='success'."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        item = _item("res4")
        session.add(item)
        await session.flush()
        session.add(ItemAnalysisORM(item_id=item.id, coefficient=0.7))
        await session.commit()

    trinity = _trinity()
    await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(AnalysisRunORM).where(AnalysisRunORM.kind == "research")
        )
        run = result.scalars().first()
        assert run is not None
        assert run.kind == "research"
        assert run.status == "success"
        assert run.started_at is not None
        assert run.finished_at is not None
        assert run.stats is not None
        assert run.stats.get("researched") == 1


@pytest.mark.asyncio
async def test_competitors_found_accumulates(analysis_sessionmaker, monkeypatch) -> None:
    """stats.competitors_found накапливает конкурентов по всем item'ам."""
    _patch_prompt(monkeypatch)

    multi_result = ResearchResult(
        summary="Summary",
        competitors=[
            Competitor(name="A", url="https://a.io"),
            Competitor(name="B", url="https://b.io"),
        ],
        sources=_SOURCES,
        maturity_signal=0.5,
        potential_signal=0.5,
        confidence=0.8,
    )

    monkeypatch.setattr(
        "analysis.research.researcher.parse_research",
        lambda text, sources: multi_result,
    )

    async with analysis_sessionmaker() as session:
        item1 = _item("res5a")
        item2 = _item("res5b")
        session.add_all([item1, item2])
        await session.flush()
        session.add(ItemAnalysisORM(item_id=item1.id, coefficient=0.7))
        session.add(ItemAnalysisORM(item_id=item2.id, coefficient=0.6))
        await session.commit()

    trinity = _trinity()
    stats = await run_research(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        limit=100,
        model="test-model",
    )

    assert stats.researched == 2
    assert stats.competitors_found == 4  # 2 items × 2 competitors each
