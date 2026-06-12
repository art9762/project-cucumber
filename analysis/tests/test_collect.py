"""Тесты прокси-роутера /collect/* (analysis-шлюз для collector).

Подход: мокаем httpx.AsyncClient через pytest monkeypatch / unittest.mock.
Используем тот же паттерн что test_categories_api.py — FastAPI TestClient +
dependency_overrides для get_current_user.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analysis.api.routers import collect as collect_mod
from analysis.auth.dependencies import get_current_user
from analysis.storage.orm import UserORM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(role: str) -> UserORM:
    return UserORM(username="tester", password_hash="x", role=role, is_active=True)


def _make_app(role: str = "admin") -> FastAPI:
    app = FastAPI()
    app.include_router(collect_mod.router)
    app.dependency_overrides[get_current_user] = lambda: _make_user(role)
    return app


def _mock_response(status_code: int, json_data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "", request=MagicMock(), response=resp
        )
    return resp


def _make_async_client(mock_resp: MagicMock) -> MagicMock:
    """Собрать AsyncClient-контекстный менеджер с заготовленным ответом."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=mock_resp)
    client.post = AsyncMock(return_value=mock_resp)
    client.put = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Admin guard — viewer/unauthenticated → 403/401
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,expected", [("viewer", 403)])
def test_sources_admin_guard(role: str, expected: int) -> None:
    client = TestClient(_make_app(role))
    assert client.get("/collect/sources").status_code == expected


@pytest.mark.parametrize("role,expected", [("viewer", 403)])
def test_create_job_admin_guard(role: str, expected: int) -> None:
    client = TestClient(_make_app(role))
    assert client.post("/collect/jobs", json={"source": "arxiv"}).status_code == expected


@pytest.mark.parametrize("role,expected", [("viewer", 403)])
def test_get_job_admin_guard(role: str, expected: int) -> None:
    client = TestClient(_make_app(role))
    assert client.get("/collect/jobs/00000000-0000-0000-0000-000000000001").status_code == expected


@pytest.mark.parametrize("role,expected", [("viewer", 403)])
def test_get_schedule_admin_guard(role: str, expected: int) -> None:
    client = TestClient(_make_app(role))
    assert client.get("/collect/schedule").status_code == expected


@pytest.mark.parametrize("role,expected", [("viewer", 403)])
def test_update_schedule_admin_guard(role: str, expected: int) -> None:
    client = TestClient(_make_app(role))
    assert client.put("/collect/schedule/arxiv", json={"cron": ""}).status_code == expected


def test_unauthenticated_returns_401() -> None:
    """Нет куки → 401 (get_current_user бросает 401, require_role его оборачивает)."""
    app = FastAPI()
    app.include_router(collect_mod.router)
    # нет override → реальный get_current_user → 401
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/collect/sources").status_code == 401


# ---------------------------------------------------------------------------
# Proxying — admin sees correct responses
# ---------------------------------------------------------------------------

def test_get_sources_proxies_health() -> None:
    health_resp = _mock_response(200, {"status": "ok", "sources": ["arxiv", "github"]})
    ctx = _make_async_client(health_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.get("/collect/sources")

    assert resp.status_code == 200
    assert resp.json() == {"sources": ["arxiv", "github"]}


def test_create_job_returns_job_out() -> None:
    job_data = {
        "id": "job-1", "source": "arxiv", "status": "running",
        "since": None, "cursor": None,
        "stats": {"fetched": 0, "inserted": 0, "updated": 0, "skipped": 0},
        "error": None, "started_at": None, "finished_at": None,
    }
    job_resp = _mock_response(202, job_data)
    ctx = _make_async_client(job_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.post("/collect/jobs", json={"source": "arxiv"})

    assert resp.status_code == 202
    assert resp.json()["id"] == "job-1"
    assert resp.json()["source"] == "arxiv"


def test_get_job_proxies_correctly() -> None:
    job_data = {
        "id": "00000000-0000-0000-0000-000000000002", "source": "github", "status": "success",
        "since": None, "cursor": None,
        "stats": {"fetched": 5, "inserted": 3, "updated": 2, "skipped": 0},
        "error": None, "started_at": None, "finished_at": None,
    }
    job_resp = _mock_response(200, job_data)
    ctx = _make_async_client(job_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.get("/collect/jobs/00000000-0000-0000-0000-000000000002")

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_get_schedule_proxies() -> None:
    sched_data = {"schedules": {"arxiv": "", "github": "0 8 * * *", "hackernews": "", "reddit": ""}}
    sched_resp = _mock_response(200, sched_data)
    ctx = _make_async_client(sched_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.get("/collect/schedule")

    assert resp.status_code == 200
    assert resp.json()["schedules"]["github"] == "0 8 * * *"


def test_update_schedule_proxies() -> None:
    sched_data = {"schedules": {"arxiv": "0 6 * * *", "github": "", "hackernews": "", "reddit": ""}}
    sched_resp = _mock_response(200, sched_data)
    ctx = _make_async_client(sched_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.put("/collect/schedule/arxiv", json={"cron": "0 6 * * *"})

    assert resp.status_code == 200
    assert resp.json()["schedules"]["arxiv"] == "0 6 * * *"


# ---------------------------------------------------------------------------
# Collector network error → 502
# ---------------------------------------------------------------------------

def test_sources_collector_network_error_502() -> None:
    client_mock = AsyncMock()
    client_mock.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_mock)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.get("/collect/sources")

    assert resp.status_code == 502
    assert "collector unavailable" in resp.json()["detail"]


def test_create_job_network_error_502() -> None:
    client_mock = AsyncMock()
    client_mock.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_mock)
    ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.post("/collect/jobs", json={"source": "arxiv"})

    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Collector 4xx errors propagated
# ---------------------------------------------------------------------------

def test_update_schedule_invalid_cron_400() -> None:
    err_resp = _mock_response(400, {"detail": "invalid cron"})
    ctx = _make_async_client(err_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.put("/collect/schedule/arxiv", json={"cron": "bad cron"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid cron"


def test_update_schedule_unknown_source_404() -> None:
    err_resp = _mock_response(404, {"detail": "unknown source"})
    ctx = _make_async_client(err_resp)

    with patch("analysis.api.routers.collect.httpx.AsyncClient", return_value=ctx):
        client = TestClient(_make_app())
        resp = client.put("/collect/schedule/nope", json={"cron": ""})

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Input validation — path segment safety
# ---------------------------------------------------------------------------

def test_traversal_source_rejected() -> None:
    client = TestClient(_make_app())
    resp = client.put("/collect/schedule/..%2Fjobs", json={"cron": ""})
    assert resp.status_code == 404


def test_invalid_job_id_rejected() -> None:
    client = TestClient(_make_app())
    resp = client.get("/collect/jobs/not-a-uuid")
    assert resp.status_code == 422
