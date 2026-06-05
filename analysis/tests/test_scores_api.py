"""Тесты API скоринга — FastAPI TestClient с моками слоя score/scorer.

Подход: для GET-эндпоинтов с реальными данными переопределяем get_analysis_session
через dependency_overrides, подставляя сессию из conftest analysis_sessionmaker.
Для POST /score патчим run_scoring (ленивый импорт внутри обработчика).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analysis.api.routers import scores as scores_mod
from analysis.score.models import ScoreStats
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Собрать минимальное FastAPI-приложение с роутером скоринга."""
    app = FastAPI()
    app.include_router(scores_mod.router)
    return app


def _fake_session_override(sessionmaker):
    """Вернуть FastAPI dependency, выдающую сессию из переданного sessionmaker."""
    async def _override():
        async with sessionmaker() as session:
            yield session
    return _override


# ---------------------------------------------------------------------------
# Фикстуры: сеянные данные
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def seeded_db(analysis_sessionmaker):
    """Засеять ItemReadORM + два ItemAnalysisORM (S и B тиры) в SQLite."""
    item_s_id = uuid.uuid4()
    item_b_id = uuid.uuid4()
    cat_id = uuid.uuid4()

    scores_s = {
        "relevance": 0.9,
        "complexity": 0.2,
        "novelty": 0.8,
        "maturity": 0.1,
        "potential": 0.85,
    }
    scores_b = {
        "relevance": 0.5,
        "complexity": 0.4,
        "novelty": 0.5,
        "maturity": 0.3,
        "potential": 0.5,
    }

    async with analysis_sessionmaker() as session:
        session.add(ItemReadORM(
            id=item_s_id,
            source="hn",
            external_id="1001",
            title="Item S Title",
            url="https://example.com/s",
        ))
        session.add(ItemReadORM(
            id=item_b_id,
            source="hn",
            external_id="1002",
            title="Item B Title",
            url="https://example.com/b",
        ))
        await session.flush()

        session.add(ItemAnalysisORM(
            item_id=item_s_id,
            category_id=cat_id,
            scores=scores_s,
            coefficient=0.82,
            tier="S",
            model_used="m",
        ))
        session.add(ItemAnalysisORM(
            item_id=item_b_id,
            category_id=None,
            scores=scores_b,
            coefficient=0.55,
            tier="B",
            model_used="m",
        ))
        await session.commit()

    return {
        "sessionmaker": analysis_sessionmaker,
        "item_s_id": item_s_id,
        "item_b_id": item_b_id,
        "cat_id": cat_id,
        "scores_s": scores_s,
        "scores_b": scores_b,
    }


# ---------------------------------------------------------------------------
# GET /tierlist
# ---------------------------------------------------------------------------

def test_tierlist_returns_all_ordered_by_coefficient(seeded_db) -> None:
    """GET /tierlist возвращает все items по coefficient убывающе."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/tierlist")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # S-тир (0.82) первым
    assert data[0]["tier"] == "S"
    assert data[0]["coefficient"] == pytest.approx(0.82, abs=1e-6)
    assert data[1]["tier"] == "B"
    assert data[1]["coefficient"] == pytest.approx(0.55, abs=1e-6)


def test_tierlist_filter_by_tier(seeded_db) -> None:
    """GET /tierlist?tier=S возвращает только S-тир."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/tierlist?tier=S")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tier"] == "S"
    assert data[0]["item_id"] == str(seeded_db["item_s_id"])


def test_tierlist_filter_by_category_id(seeded_db) -> None:
    """GET /tierlist?category_id=... фильтрует по категории."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    cat_id = seeded_db["cat_id"]
    resp = client.get(f"/tierlist?category_id={cat_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["category_id"] == str(cat_id)


def test_tierlist_limit(seeded_db) -> None:
    """GET /tierlist?limit=1 возвращает не более одного элемента."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/tierlist?limit=1")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tier"] == "S"


# ---------------------------------------------------------------------------
# GET /items/{item_id}/score
# ---------------------------------------------------------------------------

def test_get_item_score_returns_200(seeded_db) -> None:
    """GET /items/{item_id}/score → 200 с полными данными скоринга."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    item_id = seeded_db["item_s_id"]
    resp = client.get(f"/items/{item_id}/score")

    assert resp.status_code == 200
    body = resp.json()
    assert body["item_id"] == str(item_id)
    assert body["tier"] == "S"
    assert body["coefficient"] == pytest.approx(0.82, abs=1e-6)
    assert body["model_used"] == "m"
    assert body["scores"] == seeded_db["scores_s"]
    assert body["category_id"] == str(seeded_db["cat_id"])


def test_get_item_score_404_unknown_id(seeded_db) -> None:
    """GET /items/{random_uuid}/score → 404, если item_analysis строки нет."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get(f"/items/{uuid.uuid4()}/score")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /score
# ---------------------------------------------------------------------------

def test_post_score_returns_stats() -> None:
    """POST /score → 200 с полями seen/scored/escalated/failed/tier_counts/errors."""
    fake_stats = ScoreStats(
        seen=10,
        scored=8,
        escalated=2,
        failed=1,
        tier_counts={"S": 3, "A": 5},
        errors=["some error"],
    )
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.score.scorer.run_scoring", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/score")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seen"] == 10
    assert body["scored"] == 8
    assert body["escalated"] == 2
    assert body["failed"] == 1
    assert body["tier_counts"] == {"S": 3, "A": 5}
    assert body["errors"] == ["some error"]


def test_post_score_with_limit() -> None:
    """POST /score?limit=5 передаёт limit=5 в run_scoring."""
    fake_stats = ScoreStats(seen=5, scored=5, escalated=0, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.score.scorer.run_scoring", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/score?limit=5")

    assert resp.status_code == 200
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["limit"] == 5
