"""Тесты API поиска/эмбеддинга — FastAPI TestClient с моками embed-слоя.

Подход: dependency_overrides для get_analysis_session (как в test_scores_api).
Хэндлеры роутера лениво импортируют функции из реальных модулей
``analysis.embed.search`` / ``analysis.embed.embedder`` внутри тела — поэтому
мокаем их атрибуты прямо на этих модулях (patch.object). Так тест устойчив к
порядку импортов в полном прогоне и не грузит fastembed: реальный Encoder
подменяется через ``search_mod._get_encoder``, а run_embedding/search_by_text/
find_competitors замоканы и до настоящего кода эмбеддинга не доходят.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import analysis.embed.embedder as embedder_mod
import analysis.embed.search as search_impl_mod
from analysis.api.routers import search as search_mod
from analysis.auth.dependencies import get_current_user
from analysis.embed.models import EmbedStats, SearchHit
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import UserORM


def _make_fake_encoder() -> MagicMock:
    """Фейковый Encoder с детерминированным encode (вектор длиной 384)."""
    enc = MagicMock()
    enc.encode = MagicMock(return_value=[0.1] * 384)
    enc.encode_batch = MagicMock(return_value=[[0.1] * 384])
    enc.model_name = "fake-model"
    enc.dim = 384
    return enc


def _make_app() -> FastAPI:
    """Минимальное FastAPI-приложение с роутером поиска.

    Авторизацию обходим: подменяем get_current_user на фейкового admin.
    """
    app = FastAPI()
    app.include_router(search_mod.router)
    app.dependency_overrides[get_current_user] = lambda: UserORM(
        username="tester", password_hash="x", role="admin", is_active=True
    )
    return app


def _fake_session_override(sessionmaker: Any):
    """FastAPI dependency, выдающая сессию из переданного sessionmaker."""

    async def _override():
        async with sessionmaker() as session:
            yield session

    return _override


def _make_hit(
    item_id: str | None = None,
    distance: float = 0.1,
    similarity: float = 0.9,
    tier: str | None = "A",
) -> SearchHit:
    return SearchHit(
        item_id=item_id or str(uuid.uuid4()),
        title="Test Item",
        url="https://example.com/test",
        distance=distance,
        similarity=similarity,
        tier=tier,
        coefficient=0.75,
        category_id=str(uuid.uuid4()),
    )


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


def test_post_search_returns_hits(analysis_sessionmaker) -> None:
    """POST /search → 200 список SearchHitOut, сортировка сохраняется."""
    hit_a = _make_hit(distance=0.05, similarity=0.95, tier="S")
    hit_b = _make_hit(distance=0.3, similarity=0.7, tier="B")

    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(
        search_impl_mod, "search_by_text", AsyncMock(return_value=[hit_a, hit_b])
    ), patch.object(search_mod, "_get_encoder", return_value=_make_fake_encoder()):
        client = TestClient(app)
        resp = client.post("/search", json={"query": "some query", "limit": 10})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["tier"] == "S"
    assert data[0]["distance"] == pytest.approx(0.05, abs=1e-6)
    assert data[0]["similarity"] == pytest.approx(0.95, abs=1e-6)
    assert data[1]["tier"] == "B"


def test_post_search_empty_results(analysis_sessionmaker) -> None:
    """POST /search → 200 пустой список, если нет эмбеддингов."""
    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(
        search_impl_mod, "search_by_text", AsyncMock(return_value=[])
    ), patch.object(search_mod, "_get_encoder", return_value=_make_fake_encoder()):
        client = TestClient(app)
        resp = client.post("/search", json={"query": "nothing", "limit": 5})

    assert resp.status_code == 200
    assert resp.json() == []


def test_post_search_maps_all_fields(analysis_sessionmaker) -> None:
    """POST /search → SearchHitOut содержит все поля SearchHit."""
    cat_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    hit = SearchHit(
        item_id=item_id,
        title="My Title",
        url="https://example.com/item",
        distance=0.2,
        similarity=0.8,
        tier="C",
        coefficient=0.6,
        category_id=cat_id,
    )

    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(
        search_impl_mod, "search_by_text", AsyncMock(return_value=[hit])
    ), patch.object(search_mod, "_get_encoder", return_value=_make_fake_encoder()):
        client = TestClient(app)
        resp = client.post("/search", json={"query": "test", "limit": 10})

    assert resp.status_code == 200
    body = resp.json()[0]
    assert body["item_id"] == item_id
    assert body["title"] == "My Title"
    assert body["url"] == "https://example.com/item"
    assert body["distance"] == pytest.approx(0.2, abs=1e-6)
    assert body["similarity"] == pytest.approx(0.8, abs=1e-6)
    assert body["tier"] == "C"
    assert body["coefficient"] == pytest.approx(0.6, abs=1e-6)
    assert body["category_id"] == cat_id


# ---------------------------------------------------------------------------
# GET /items/{item_id}/competitors
# ---------------------------------------------------------------------------


def test_get_competitors_returns_hits(analysis_sessionmaker) -> None:
    """GET /items/{id}/competitors → 200 список конкурентов."""
    item_id = uuid.uuid4()
    competitor = _make_hit(distance=0.15, similarity=0.85, tier="A")

    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(
        search_impl_mod, "find_competitors", AsyncMock(return_value=[competitor])
    ):
        client = TestClient(app)
        resp = client.get(f"/items/{item_id}/competitors?limit=5")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["tier"] == "A"
    assert data[0]["distance"] == pytest.approx(0.15, abs=1e-6)
    assert data[0]["similarity"] == pytest.approx(0.85, abs=1e-6)


def test_get_competitors_no_embedding_returns_empty(analysis_sessionmaker) -> None:
    """GET /items/{id}/competitors → пустой список, если нет вектора."""
    item_id = uuid.uuid4()

    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(search_impl_mod, "find_competitors", AsyncMock(return_value=[])):
        client = TestClient(app)
        resp = client.get(f"/items/{item_id}/competitors")

    assert resp.status_code == 200
    assert resp.json() == []


def test_get_competitors_default_limit(analysis_sessionmaker) -> None:
    """GET /items/{id}/competitors без limit= использует default=10."""
    item_id = uuid.uuid4()
    mock_find = AsyncMock(return_value=[])

    app = _make_app()
    app.dependency_overrides[get_analysis_session] = _fake_session_override(
        analysis_sessionmaker
    )

    with patch.object(search_impl_mod, "find_competitors", mock_find):
        client = TestClient(app)
        client.get(f"/items/{item_id}/competitors")

    _, call_kwargs = mock_find.call_args
    assert call_kwargs.get("limit", 10) == 10


# ---------------------------------------------------------------------------
# POST /embed
# ---------------------------------------------------------------------------


def test_post_embed_returns_stats() -> None:
    """POST /embed → 200 с полями EmbedRunOut, маппинг EmbedStats."""
    fake_stats = EmbedStats(
        seen=20,
        embedded=18,
        failed=2,
        model="BAAI/bge-small-en-v1.5",
        dim=384,
        errors=["item 5 failed"],
    )
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()

    with patch.object(embedder_mod, "run_embedding", mock_run), patch.object(
        search_mod, "_get_encoder", return_value=_make_fake_encoder()
    ):
        client = TestClient(app)
        resp = client.post("/embed")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seen"] == 20
    assert body["embedded"] == 18
    assert body["failed"] == 2
    assert body["model"] == "BAAI/bge-small-en-v1.5"
    assert body["dim"] == 384
    assert body["errors"] == ["item 5 failed"]


def test_post_embed_with_limit() -> None:
    """POST /embed?limit=5 передаёт limit=5 в run_embedding."""
    fake_stats = EmbedStats(seen=5, embedded=5, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()

    with patch.object(embedder_mod, "run_embedding", mock_run), patch.object(
        search_mod, "_get_encoder", return_value=_make_fake_encoder()
    ):
        client = TestClient(app)
        resp = client.post("/embed?limit=5")

    assert resp.status_code == 200
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["limit"] == 5


def test_post_embed_no_limit() -> None:
    """POST /embed без limit= передаёт limit=None в run_embedding."""
    fake_stats = EmbedStats(seen=0, embedded=0, failed=0)
    mock_run = AsyncMock(return_value=fake_stats)

    app = _make_app()

    with patch.object(embedder_mod, "run_embedding", mock_run), patch.object(
        search_mod, "_get_encoder", return_value=_make_fake_encoder()
    ):
        client = TestClient(app)
        client.post("/embed")

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["limit"] is None
