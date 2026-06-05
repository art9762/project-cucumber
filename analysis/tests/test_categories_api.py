"""Тесты API категорий — FastAPI TestClient с моками слоя categories/classifier.

Подход: мокаем функции репозитория на уровне модуля роутера (аналогично тому,
как test_health.py патчит sessionmaker). Это надёжнее, чем dependency_overrides
с async SQLite, потому что TestClient запускает свой event loop, а in-memory
SQLite Engine привязан к loop из фикстуры conftest.

Для POST /classify дополнительно патчим run_classification — символ, импортируемый
лениво внутри обработчика.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from analysis.api.routers import categories as cat_mod
from analysis.auth.dependencies import get_current_user
from analysis.classify.models import CategoryNode, ClassifyStats
from analysis.storage.orm import UserORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_node(
    slug: str,
    title: str,
    *,
    approved: bool = True,
    parent_id: uuid.UUID | None = None,
    node_id: uuid.UUID | None = None,
) -> CategoryNode:
    """Создать CategoryNode с заданными полями."""
    return CategoryNode(
        id=node_id or uuid.uuid4(),
        slug=slug,
        title=title,
        parent_id=parent_id,
        approved=approved,
    )


def _make_app() -> FastAPI:
    """Собрать минимальное FastAPI-приложение с роутером категорий.

    Авторизацию обходим: подменяем get_current_user на фейкового admin —
    этого достаточно и для read-гейтов (get_current_user), и для admin-гейтов
    (require_role зависит от get_current_user).
    """
    app = FastAPI()
    app.include_router(cat_mod.router)
    app.dependency_overrides[get_current_user] = lambda: UserORM(
        username="tester", password_hash="x", role="admin", is_active=True
    )
    return app


# ---------------------------------------------------------------------------
# GET /categories — вложенное дерево
# ---------------------------------------------------------------------------

def test_get_categories_tree_nested() -> None:
    """GET /categories возвращает вложенное дерево: дочерний узел в children родителя."""
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent = _make_node("tech", "Технологии", node_id=parent_id)
    child = _make_node("ai", "ИИ", parent_id=parent_id, node_id=child_id)

    async def _load_tree(session):
        return [parent, child]

    app = _make_app()
    with patch.object(cat_mod, "load_category_tree", _load_tree):
        # Перекрыть get_analysis_session фиктивной зависимостью.
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield None

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.get("/categories")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1  # один корень
    root = data[0]
    assert root["slug"] == "tech"
    assert len(root["children"]) == 1
    assert root["children"][0]["slug"] == "ai"


def test_get_categories_tree_empty() -> None:
    """GET /categories на пустой БД возвращает пустой список."""
    async def _load_tree(session):
        return []

    app = _make_app()
    with patch.object(cat_mod, "load_category_tree", _load_tree):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield None

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.get("/categories")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /categories/pending
# ---------------------------------------------------------------------------

def test_get_pending_returns_only_unapproved() -> None:
    """GET /categories/pending возвращает только approved=False."""
    pending1 = _make_node("pending-a", "Ожидание A", approved=False)
    pending2 = _make_node("pending-b", "Ожидание B", approved=False)

    async def _list_pending(session):
        return [pending1, pending2]

    app = _make_app()
    with patch.object(cat_mod, "list_pending", _list_pending):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield None

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.get("/categories/pending")

    assert resp.status_code == 200
    data = resp.json()
    slugs = {item["slug"] for item in data}
    assert slugs == {"pending-a", "pending-b"}
    assert all(item["approved"] is False for item in data)


def test_get_pending_empty() -> None:
    """GET /categories/pending возвращает пустой список, если нет неутверждённых."""
    async def _list_pending(session):
        return []

    app = _make_app()
    with patch.object(cat_mod, "list_pending", _list_pending):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield None

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.get("/categories/pending")

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /categories/{id}/approve
# ---------------------------------------------------------------------------

def test_approve_category_ok() -> None:
    """POST /categories/{id}/approve → 200 + ok=True с approved=True."""
    cat_id = uuid.uuid4()
    node = _make_node("pending", "Ожидание", approved=True, node_id=cat_id)

    async def _set_approved(session, category_id, approved):
        assert category_id == cat_id
        assert approved is True
        return node

    app = _make_app()
    with patch.object(cat_mod, "set_approved", _set_approved):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            # Нужна сессия с commit() — возвращаем AsyncMock.
            s = AsyncMock()
            yield s

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.post(f"/categories/{cat_id}/approve")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["id"] == str(cat_id)
    assert body["approved"] is True


def test_approve_category_not_found() -> None:
    """POST /categories/{id}/approve → 404, если категория не найдена."""
    async def _set_approved(session, category_id, approved):
        return None

    app = _make_app()
    with patch.object(cat_mod, "set_approved", _set_approved):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.post(f"/categories/{uuid.uuid4()}/approve")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /categories/{id}/reject
# ---------------------------------------------------------------------------

def test_reject_category_ok() -> None:
    """POST /categories/{id}/reject → 200 + ok=True при успешном удалении."""
    cat_id = uuid.uuid4()

    async def _delete_category(session, category_id):
        assert category_id == cat_id
        return True

    app = _make_app()
    with patch.object(cat_mod, "delete_category", _delete_category):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.post(f"/categories/{cat_id}/reject")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["id"] == str(cat_id)


def test_reject_category_not_found() -> None:
    """POST /categories/{id}/reject → 404, если категория не найдена."""
    async def _delete_category(session, category_id):
        return False

    app = _make_app()
    with patch.object(cat_mod, "delete_category", _delete_category):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)
        resp = client.post(f"/categories/{uuid.uuid4()}/reject")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /classify
# ---------------------------------------------------------------------------

def test_classify_returns_stats() -> None:
    """POST /classify → 200 с полями seen/classified/suggested/failed/errors."""
    stats = ClassifyStats(seen=5, classified=4, suggested=1, failed=1, errors=["err1"])

    mock_run = AsyncMock(return_value=stats)

    app = _make_app()
    # Все три символа (run_classification, get_trinity_client, sessionmaker'ы)
    # импортируются лениво внутри обработчика — патчим их в исходных модулях.
    with patch("analysis.classify.classifier.run_classification", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_read_sessionmaker", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/classify")

    assert resp.status_code == 200
    body = resp.json()
    assert body["seen"] == 5
    assert body["classified"] == 4
    assert body["suggested"] == 1
    assert body["failed"] == 1
    assert body["errors"] == ["err1"]


def test_classify_with_limit() -> None:
    """POST /classify?limit=10 передаёт limit в run_classification."""
    stats = ClassifyStats(seen=2, classified=2, suggested=0, failed=0, errors=[])
    mock_run = AsyncMock(return_value=stats)

    app = _make_app()
    with patch("analysis.classify.classifier.run_classification", mock_run, create=True), \
         patch("analysis.trinity.get_trinity_client", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_read_sessionmaker", return_value=AsyncMock()), \
         patch("analysis.storage.db.get_analysis_sessionmaker", return_value=AsyncMock()):
        client = TestClient(app)
        resp = client.post("/classify?limit=10")

    assert resp.status_code == 200
    # Проверяем, что run_classification вызван с limit=10
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["limit"] == 10


# ---------------------------------------------------------------------------
# Интеграционный тест: approve → pending пустой
# ---------------------------------------------------------------------------

def test_approve_removes_from_pending() -> None:
    """После approve категория пропадает из /categories/pending."""
    cat_id = uuid.uuid4()
    node_pending = _make_node("new-cat", "Новая категория", approved=False, node_id=cat_id)
    node_approved = _make_node("new-cat", "Новая категория", approved=True, node_id=cat_id)

    # Имитируем pending с одним узлом, после approve — пустой список.
    pending_list: list[CategoryNode] = [node_pending]

    async def _list_pending(session):
        return list(pending_list)

    async def _set_approved(session, category_id, approved):
        pending_list.clear()
        return node_approved

    app = _make_app()
    with patch.object(cat_mod, "list_pending", _list_pending), \
         patch.object(cat_mod, "set_approved", _set_approved):
        from analysis.storage.db import get_analysis_session

        async def _fake_session():
            yield AsyncMock()

        app.dependency_overrides[get_analysis_session] = _fake_session
        client = TestClient(app)

        # До approve — один pending.
        resp1 = client.get("/categories/pending")
        assert resp1.status_code == 200
        assert len(resp1.json()) == 1

        # Approve.
        resp2 = client.post(f"/categories/{cat_id}/approve")
        assert resp2.status_code == 200

        # После approve — pending пуст.
        resp3 = client.get("/categories/pending")
        assert resp3.status_code == 200
        assert resp3.json() == []
