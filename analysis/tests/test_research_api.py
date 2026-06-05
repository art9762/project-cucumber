"""Тесты API ресёрча — FastAPI TestClient с моками слоя research/researcher.

Подход: для GET-эндпоинтов с реальными данными переопределяем get_analysis_session
через dependency_overrides, подставляя сессию из conftest analysis_sessionmaker.
Для POST /research патчим run_research (ленивый импорт внутри обработчика).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analysis.api.routers import research as research_mod
from analysis.research.models import ResearchStats
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import ItemReadORM, ItemResearchORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_app() -> FastAPI:
    """Собрать минимальное FastAPI-приложение с роутером ресёрча."""
    app = FastAPI()
    app.include_router(research_mod.router)
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
    """Засеять ItemReadORM + ItemResearchORM в SQLite."""
    item_id = uuid.uuid4()
    item_no_competitors_id = uuid.uuid4()
    item_no_research_id = uuid.uuid4()

    competitors_data = [
        {"name": "CompetitorA", "url": "https://comp-a.io", "note": "main rival"},
        {"name": "CompetitorB", "url": None, "note": None},
    ]

    async with analysis_sessionmaker() as session:
        session.add(ItemReadORM(
            id=item_id,
            source="hn",
            external_id="2001",
            title="Research Item Title",
            url="https://example.com/research-item",
        ))
        session.add(ItemReadORM(
            id=item_no_competitors_id,
            source="hn",
            external_id="2002",
            title="No Competitors Item",
            url="https://example.com/no-comp",
        ))
        session.add(ItemReadORM(
            id=item_no_research_id,
            source="hn",
            external_id="2003",
            title="Unresearched Item",
            url="https://example.com/unresearched",
        ))
        await session.flush()

        session.add(ItemResearchORM(
            item_id=item_id,
            summary="This is a great idea with lots of competition.",
            competitors=competitors_data,
            sources=["https://source1.com", "https://source2.com"],
            maturity_signal=0.7,
            potential_signal=0.8,
            model_used="claude-3-sonnet",
        ))
        session.add(ItemResearchORM(
            item_id=item_no_competitors_id,
            summary="Blue ocean idea, no competitors found.",
            competitors=[],
            sources=["https://source3.com"],
            maturity_signal=0.2,
            potential_signal=0.9,
            model_used="claude-3-haiku",
        ))
        await session.commit()

    return {
        "sessionmaker": analysis_sessionmaker,
        "item_id": item_id,
        "item_no_competitors_id": item_no_competitors_id,
        "item_no_research_id": item_no_research_id,
        "competitors_data": competitors_data,
    }


# ---------------------------------------------------------------------------
# GET /items/{item_id}/research
# ---------------------------------------------------------------------------

def test_get_item_research_returns_200(seeded_db) -> None:
    """GET /items/{item_id}/research → 200 с полными данными ресёрча."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    item_id = seeded_db["item_id"]
    resp = client.get(f"/items/{item_id}/research")

    assert resp.status_code == 200
    body = resp.json()
    assert body["item_id"] == str(item_id)
    assert body["title"] == "Research Item Title"
    assert body["url"] == "https://example.com/research-item"
    assert body["summary"] == "This is a great idea with lots of competition."
    assert len(body["competitors"]) == 2
    assert body["competitors"][0]["name"] == "CompetitorA"
    assert body["competitors"][0]["url"] == "https://comp-a.io"
    assert body["competitors"][0]["note"] == "main rival"
    assert body["competitors"][1]["name"] == "CompetitorB"
    assert body["competitors"][1]["url"] is None
    assert body["sources"] == ["https://source1.com", "https://source2.com"]
    assert body["maturity_signal"] == pytest.approx(0.7, abs=1e-6)
    assert body["potential_signal"] == pytest.approx(0.8, abs=1e-6)
    assert body["model_used"] == "claude-3-sonnet"


def test_get_item_research_404_on_missing_research(seeded_db) -> None:
    """GET /items/{item_id}/research → 404 когда нет строки item_research."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    item_id = seeded_db["item_no_research_id"]
    resp = client.get(f"/items/{item_id}/research")

    assert resp.status_code == 404


def test_get_item_research_404_on_unknown_id(seeded_db) -> None:
    """GET /items/{random_uuid}/research → 404 для несуществующего id."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get(f"/items/{uuid.uuid4()}/research")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /research
# ---------------------------------------------------------------------------

def test_list_research_returns_all(seeded_db) -> None:
    """GET /research возвращает все researched items."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/research")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


def test_list_research_filter_has_competitors_true(seeded_db) -> None:
    """GET /research?has_competitors=true возвращает только items с конкурентами."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/research?has_competitors=true")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["item_id"] == str(seeded_db["item_id"])
    assert len(data[0]["competitors"]) > 0


def test_list_research_filter_has_competitors_false(seeded_db) -> None:
    """GET /research?has_competitors=false возвращает только items без конкурентов."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/research?has_competitors=false")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["item_id"] == str(seeded_db["item_no_competitors_id"])
    assert len(data[0]["competitors"]) == 0


def test_list_research_limit(seeded_db) -> None:
    """GET /research?limit=1 возвращает не более одного элемента."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        seeded_db["sessionmaker"]
    )
    client = TestClient(app)
    resp = client.get("/research?limit=1")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


# ---------------------------------------------------------------------------
# POST /research
# ---------------------------------------------------------------------------

def test_post_research_returns_stats() -> None:
    """POST /research → 200 с полями seen/researched/competitors_found/failed/errors."""
    fake_stats = ResearchStats(
        seen=10,
        researched=8,
        competitors_found=15,
        failed=1,
        errors=["some error"],
    )
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.research.researcher.run_research", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/research")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seen"] == 10
    assert body["researched"] == 8
    assert body["competitors_found"] == 15
    assert body["failed"] == 1
    assert body["errors"] == ["some error"]


def test_post_research_with_limit() -> None:
    """POST /research?limit=5 передаёт limit=5 в run_research."""
    fake_stats = ResearchStats(seen=5, researched=5, competitors_found=3, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.research.researcher.run_research", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/research?limit=5")

    assert resp.status_code == 200
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["limit"] == 5


def test_post_research_with_min_tier() -> None:
    """POST /research?min_tier=A передаёт min_tier='A' в run_research."""
    fake_stats = ResearchStats(seen=3, researched=3, competitors_found=5, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.research.researcher.run_research", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/research?min_tier=A")

    assert resp.status_code == 200
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["min_tier"] == "A"


def test_post_research_with_min_coefficient() -> None:
    """POST /research?min_coefficient=0.7 передаёт min_coefficient=0.7 в run_research."""
    fake_stats = ResearchStats(seen=2, researched=2, competitors_found=2, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()
    with patch("analysis.research.researcher.run_research", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/research?min_coefficient=0.7")

    assert resp.status_code == 200
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["min_coefficient"] == pytest.approx(0.7, abs=1e-6)
