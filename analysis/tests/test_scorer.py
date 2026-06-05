"""Тесты оркестратора скоринга (без Postgres, без сети).

Использует общую фикстуру ``analysis_sessionmaker`` из conftest.py.
build_score_prompt и parse_scores заглушаются через monkeypatch — тест
hermetic и не зависит от деталей промпта/парсинга.
compute_coefficient/assign_tier используются настоящие через ScoringConfig.default().
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from analysis.score.models import ScoreParams, ScoreResult, ScoringConfig
from analysis.score.scorer import run_scoring
from analysis.storage.orm import AnalysisRunORM, ItemAnalysisORM, ItemReadORM, CategoryORM


# ---------------------------------------------------------------------------
# Константы для детерминированных тестов
# ---------------------------------------------------------------------------

_CONFIG = ScoringConfig.default()

# Параметры, при которых should_escalate(res, coef, config) == False
# и confidence выше порога.  Коэффициент = 0.15 + 0.45*0.8 + 0.20*0.6 + 0.20*0.7
#   - 0.10*0.3 - 0.15*0.2  ≈  0.15 + 0.36 + 0.12 + 0.14 - 0.03 - 0.03 = 0.71 → тир A.
_GOOD_PARAMS = ScoreParams(
    relevance=0.8, complexity=0.3, novelty=0.6, maturity=0.2, potential=0.7
)
_GOOD_RESULT = ScoreResult(params=_GOOD_PARAMS, confidence=0.9, rationale="ok")

# Параметры с низкой уверенностью → should_escalate вернёт True.
_LOW_CONF_RESULT = ScoreResult(
    params=_GOOD_PARAMS,
    confidence=0.3,  # ниже escalate_min_confidence=0.55
    rationale="low",
)

_STUB_SYSTEM = "sys"
_STUB_MESSAGES = [{"role": "user", "content": "x"}]


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _item(external_id: str, fetched_dt: datetime | None = None) -> ItemReadORM:
    """Создать тестовый ItemReadORM с уникальным external_id."""
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=fetched_dt or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def _category(slug: str = "ai") -> CategoryORM:
    """Создать тестовую CategoryORM."""
    return CategoryORM(slug=slug, title=slug.upper(), approved=True)


def _trinity(return_value: str = "{}") -> AsyncMock:
    """Создать фиктивный TrinityClient."""
    mock = AsyncMock()
    mock.complete = AsyncMock(return_value=return_value)
    return mock


def _patch_prompt(monkeypatch) -> None:  # noqa: ANN001
    """Заглушить build_score_prompt — возвращает стабильные (system, messages)."""
    monkeypatch.setattr(
        "analysis.score.scorer.build_score_prompt",
        lambda item, cat: (_STUB_SYSTEM, _STUB_MESSAGES),
    )


def _patch_parse_ok(monkeypatch, result: ScoreResult = _GOOD_RESULT) -> None:  # noqa: ANN001
    """Заглушить parse_scores — всегда возвращает result."""
    monkeypatch.setattr("analysis.score.scorer.parse_scores", lambda text: result)


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path(analysis_sessionmaker, monkeypatch) -> None:
    """После успешного прогона item_analysis обновлён, stats.scored == 1, failed == 0."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        cat = _category()
        item = _item("h1")
        session.add_all([cat, item])
        await session.commit()
        item_id = item.id
        # Создать запись item_analysis с category_id (Фаза 1) без coefficient.
        ia = ItemAnalysisORM(item_id=item.id, category_id=cat.id)
        session.add(ia)
        await session.commit()

    trinity = _trinity()
    stats = await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model="deep",
    )

    assert stats.scored == 1
    assert stats.failed == 0
    assert stats.seen == 1

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item_id)
        )
        ia = result.scalars().first()
        assert ia is not None
        assert ia.coefficient is not None
        assert isinstance(ia.coefficient, float)
        assert ia.scores is not None
        assert len(ia.scores) == 5
        assert ia.tier in ("S", "A", "B", "C", "D")
        assert ia.model_used == "cheap"


@pytest.mark.asyncio
async def test_idempotency_second_run_sees_zero(analysis_sessionmaker, monkeypatch) -> None:
    """Второй прогон не трогает уже проскоренный item: stats.seen == 0."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        cat = _category()
        item = _item("i1")
        session.add_all([cat, item])
        await session.commit()
        ia = ItemAnalysisORM(item_id=item.id, category_id=cat.id)
        session.add(ia)
        await session.commit()

    trinity = _trinity()
    await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model=None,
    )

    stats2 = await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model=None,
    )

    assert stats2.seen == 0
    assert stats2.scored == 0


@pytest.mark.asyncio
async def test_per_item_failure_does_not_abort_run(analysis_sessionmaker, monkeypatch) -> None:
    """parse_scores бросает на первом item → failed==1, scored==1, прогон не обрывается."""
    _patch_prompt(monkeypatch)

    call_count = 0

    def _parse_side_effect(text: str) -> ScoreResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("bad response")
        return _GOOD_RESULT

    monkeypatch.setattr("analysis.score.scorer.parse_scores", _parse_side_effect)

    async with analysis_sessionmaker() as session:
        cat = _category()
        item1 = _item("f1", datetime(2024, 1, 1, 1, tzinfo=timezone.utc))
        item2 = _item("f2", datetime(2024, 1, 1, 2, tzinfo=timezone.utc))
        session.add_all([cat, item1, item2])
        await session.commit()
        item2_id = item2.id
        ia1 = ItemAnalysisORM(item_id=item1.id, category_id=cat.id)
        ia2 = ItemAnalysisORM(item_id=item2.id, category_id=cat.id)
        session.add_all([ia1, ia2])
        await session.commit()

    trinity = _trinity()
    stats = await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model=None,
    )

    assert stats.seen == 2
    assert stats.failed == 1
    assert stats.scored == 1
    assert len(stats.errors) == 1

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item2_id)
        )
        ia = result.scalars().first()
        assert ia is not None
        assert ia.coefficient is not None, "Второй item должен быть проскорен"


@pytest.mark.asyncio
async def test_escalation_calls_deep_model(analysis_sessionmaker, monkeypatch) -> None:
    """Низкая уверенность → trinity.complete вызывается дважды, model_used == deep."""
    _patch_prompt(monkeypatch)

    call_count = 0

    def _parse_escalating(text: str) -> ScoreResult:
        nonlocal call_count
        call_count += 1
        # Первый вызов → низкая уверенность → эскалация.
        # Второй вызов (deep) → нормальная уверенность.
        if call_count == 1:
            return _LOW_CONF_RESULT
        return _GOOD_RESULT

    monkeypatch.setattr("analysis.score.scorer.parse_scores", _parse_escalating)

    async with analysis_sessionmaker() as session:
        cat = _category()
        item = _item("e1")
        session.add_all([cat, item])
        await session.commit()
        item_id = item.id
        ia = ItemAnalysisORM(item_id=item.id, category_id=cat.id)
        session.add(ia)
        await session.commit()

    trinity = _trinity()
    stats = await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model="deep",
    )

    assert trinity.complete.call_count == 2
    assert stats.escalated == 1
    assert stats.scored == 1

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemAnalysisORM).where(ItemAnalysisORM.item_id == item_id)
        )
        ia = result.scalars().first()
        assert ia is not None
        assert ia.model_used == "deep"


@pytest.mark.asyncio
async def test_analysis_runs_row_created_and_finalized(analysis_sessionmaker, monkeypatch) -> None:
    """После прогона в analysis_runs есть строка kind='score', status='success'."""
    _patch_prompt(monkeypatch)
    _patch_parse_ok(monkeypatch)

    async with analysis_sessionmaker() as session:
        cat = _category()
        item = _item("r1")
        session.add_all([cat, item])
        await session.commit()
        ia = ItemAnalysisORM(item_id=item.id, category_id=cat.id)
        session.add(ia)
        await session.commit()

    trinity = _trinity()
    await run_scoring(
        analysis_sessionmaker=analysis_sessionmaker,
        trinity=trinity,
        config=_CONFIG,
        limit=100,
        cheap_model="cheap",
        deep_model=None,
    )

    from sqlalchemy import select
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(AnalysisRunORM).where(AnalysisRunORM.kind == "score")
        )
        run = result.scalars().first()
        assert run is not None
        assert run.kind == "score"
        assert run.status == "success"
        assert run.started_at is not None
        assert run.finished_at is not None
        assert run.stats is not None
        assert run.stats.get("scored") == 1
