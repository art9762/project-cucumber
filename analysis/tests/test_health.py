"""Тесты GET /health — изолированы от Postgres и реального TrinityClient."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def sqlite_sessionmaker():
    """Sessionmaker на in-memory SQLite (без схемы — нужен только SELECT 1)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sm = async_sessionmaker(engine, expire_on_commit=False)
    yield sm
    await engine.dispose()


def _make_client(
    sqlite_sm: async_sessionmaker,
    *,
    trinity_configured: bool,
) -> TestClient:
    """Построить TestClient с заглушками БД и Trinity."""
    from analysis.api.routers import health as health_mod
    from analysis.main import create_app

    stub_trinity = MagicMock()
    stub_trinity.is_configured = trinity_configured

    app = create_app()

    # Монкипатч sessionmaker и get_trinity_client на уровне модуля роутера.
    import analysis.trinity as trinity_mod

    original_sm = health_mod.get_analysis_sessionmaker
    original_gtc = trinity_mod.get_trinity_client

    health_mod.get_analysis_sessionmaker = lambda: sqlite_sm  # type: ignore[assignment]
    trinity_mod.get_trinity_client = lambda: stub_trinity  # type: ignore[assignment]

    try:
        client = TestClient(app, raise_server_exceptions=True)
        yield client
    finally:
        health_mod.get_analysis_sessionmaker = original_sm
        trinity_mod.get_trinity_client = original_gtc


@pytest.fixture
def healthy_client(sqlite_sessionmaker):
    """TestClient с рабочей БД и настроенным Trinity."""
    yield from _make_client(sqlite_sessionmaker, trinity_configured=True)


@pytest.fixture
def unconfigured_trinity_client(sqlite_sessionmaker):
    """TestClient с рабочей БД, но Trinity без токена."""
    yield from _make_client(sqlite_sessionmaker, trinity_configured=False)


def test_health_ok(healthy_client: TestClient) -> None:
    """Рабочая БД + настроенный Trinity → status ok, все флаги True."""
    response = healthy_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["trinity_configured"] is True


def test_health_trinity_not_configured(unconfigured_trinity_client: TestClient) -> None:
    """БД доступна, Trinity без токена → status ok, trinity_configured False."""
    response = unconfigured_trinity_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["trinity_configured"] is False


def test_health_db_failure(sqlite_sessionmaker) -> None:
    """Недоступная БД → status degraded, database False, всегда 200."""
    from analysis.api.routers import health as health_mod
    from analysis.main import create_app
    import analysis.trinity as trinity_mod
    from sqlalchemy.ext.asyncio import async_sessionmaker as _asm, create_async_engine as _cae

    # Сессия на несуществующий хост — connect сразу даст ошибку.
    bad_engine = _cae("sqlite+aiosqlite:////nonexistent_path_xyz/bad.db")
    bad_sm = _asm(bad_engine, expire_on_commit=False)

    stub_trinity = MagicMock()
    stub_trinity.is_configured = True

    app = create_app()

    original_sm = health_mod.get_analysis_sessionmaker
    original_gtc = trinity_mod.get_trinity_client

    health_mod.get_analysis_sessionmaker = lambda: bad_sm  # type: ignore[assignment]
    trinity_mod.get_trinity_client = lambda: stub_trinity  # type: ignore[assignment]

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["database"] is False
    finally:
        health_mod.get_analysis_sessionmaker = original_sm
        trinity_mod.get_trinity_client = original_gtc
        import asyncio

        asyncio.get_event_loop().run_until_complete(bad_engine.dispose())


def test_health_response_shape(healthy_client: TestClient) -> None:
    """Ответ содержит все три обязательных поля."""
    body = healthy_client.get("/health").json()
    assert "status" in body
    assert "database" in body
    assert "trinity_configured" in body
