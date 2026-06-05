"""Тесты аутентификации/авторизации (Фаза 6).

Покрытие:
- hashing: roundtrip hash/verify, неверный пароль.
- sessions: create → resolve, истечение, revoke, неактивный пользователь.
- API: login (cookie + role), /auth/me (200/401), logout (clears cookie),
  неверный пароль → 401, admin-only эндпоинт 403 для viewer / 200 для admin.

Как и остальные API-тесты, БД — in-memory SQLite из conftest (analysis_sessionmaker).
get_analysis_session переопределяется на сессию из этого sessionmaker.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from analysis.api.routers import auth as auth_mod
from analysis.auth.dependencies import require_role
from analysis.auth.hashing import hash_password, verify_password
from analysis.auth.sessions import create_session, resolve_session, revoke_session
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import SessionORM, UserORM


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------

def test_hash_password_roundtrip() -> None:
    """verify_password принимает верный пароль и хеш не равен открытому тексту."""
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"
    assert verify_password("s3cret-pw", h) is True


def test_hash_password_wrong() -> None:
    """verify_password отклоняет неверный пароль."""
    h = hash_password("s3cret-pw")
    assert verify_password("wrong", h) is False


def test_verify_password_garbage_hash() -> None:
    """Битый хеш не роняет проверку, а возвращает False."""
    assert verify_password("anything", "not-a-real-hash") is False


# ---------------------------------------------------------------------------
# sessions (на SQLite из conftest)
# ---------------------------------------------------------------------------

async def _add_user(sessionmaker, *, role: str = "viewer", active: bool = True) -> uuid.UUID:
    uid = uuid.uuid4()
    async with sessionmaker() as session:
        session.add(
            UserORM(
                id=uid,
                username=f"u-{uid.hex[:8]}",
                password_hash=hash_password("pw"),
                role=role,
                is_active=active,
            )
        )
        await session.commit()
    return uid


async def test_session_create_and_resolve(analysis_sessionmaker) -> None:
    """create_session → resolve_session возвращает того же пользователя."""
    uid = await _add_user(analysis_sessionmaker)
    async with analysis_sessionmaker() as session:
        token = await create_session(session, uid, ttl_hours=1)
    async with analysis_sessionmaker() as session:
        user = await resolve_session(session, token)
    assert user is not None
    assert user.id == uid


async def test_session_expired(analysis_sessionmaker) -> None:
    """Истёкшая сессия не резолвится."""
    uid = await _add_user(analysis_sessionmaker)
    token = "expired-token"
    async with analysis_sessionmaker() as session:
        session.add(
            SessionORM(
                token=token,
                user_id=uid,
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        await session.commit()
    async with analysis_sessionmaker() as session:
        assert await resolve_session(session, token) is None


async def test_session_revoke(analysis_sessionmaker) -> None:
    """После revoke токен больше не резолвится."""
    uid = await _add_user(analysis_sessionmaker)
    async with analysis_sessionmaker() as session:
        token = await create_session(session, uid, ttl_hours=1)
    async with analysis_sessionmaker() as session:
        await revoke_session(session, token)
    async with analysis_sessionmaker() as session:
        assert await resolve_session(session, token) is None


async def test_session_inactive_user(analysis_sessionmaker) -> None:
    """Сессия неактивного пользователя не резолвится."""
    uid = await _add_user(analysis_sessionmaker, active=False)
    async with analysis_sessionmaker() as session:
        token = await create_session(session, uid, ttl_hours=1)
    async with analysis_sessionmaker() as session:
        assert await resolve_session(session, token) is None


async def test_resolve_unknown_token(analysis_sessionmaker) -> None:
    """Неизвестный/пустой токен → None."""
    async with analysis_sessionmaker() as session:
        assert await resolve_session(session, "nope") is None
        assert await resolve_session(session, "") is None


# ---------------------------------------------------------------------------
# API: login / me / logout
# ---------------------------------------------------------------------------

def _fake_session_override(sessionmaker):
    async def _override():
        async with sessionmaker() as session:
            yield session
    return _override


def _make_auth_app(sessionmaker) -> FastAPI:
    """Приложение с роутером auth + admin-only пробником, поверх SQLite-сессии."""
    app = FastAPI()
    app.include_router(auth_mod.router)

    @app.get("/admin-only")
    async def _admin_only(_user=Depends(require_role("admin"))) -> dict:
        return {"ok": True}

    app.dependency_overrides[get_analysis_session] = _fake_session_override(sessionmaker)
    return app


@pytest_asyncio.fixture
async def auth_client(analysis_sessionmaker):
    """TestClient + seeded admin/viewer users (пароль 'pw')."""
    async with analysis_sessionmaker() as session:
        session.add(
            UserORM(
                username="admin",
                password_hash=hash_password("pw"),
                role="admin",
                is_active=True,
            )
        )
        session.add(
            UserORM(
                username="viewer",
                password_hash=hash_password("pw"),
                role="viewer",
                is_active=True,
            )
        )
        await session.commit()
    app = _make_auth_app(analysis_sessionmaker)
    return TestClient(app)


def test_login_sets_cookie_and_returns_role(auth_client) -> None:
    """POST /auth/login → 200, тело {username, role}, выставлена session-cookie."""
    resp = auth_client.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert resp.status_code == 200
    assert resp.json() == {"username": "admin", "role": "admin"}
    assert "cucumber_session" in resp.cookies


def test_login_wrong_password_401(auth_client) -> None:
    """Неверный пароль → 401, cookie не выставлена."""
    resp = auth_client.post(
        "/auth/login", json={"username": "admin", "password": "bad"}
    )
    assert resp.status_code == 401
    assert "cucumber_session" not in resp.cookies


def test_login_unknown_user_401(auth_client) -> None:
    """Несуществующий пользователь → 401."""
    resp = auth_client.post(
        "/auth/login", json={"username": "ghost", "password": "pw"}
    )
    assert resp.status_code == 401


def test_me_without_cookie_401(auth_client) -> None:
    """GET /auth/me без cookie → 401."""
    resp = auth_client.get("/auth/me")
    assert resp.status_code == 401


def test_me_with_cookie_200(auth_client) -> None:
    """После логина GET /auth/me → 200 с {username, role}."""
    auth_client.post("/auth/login", json={"username": "viewer", "password": "pw"})
    resp = auth_client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"username": "viewer", "role": "viewer"}


def test_logout_clears_cookie_and_session(auth_client) -> None:
    """Logout: 204, /auth/me снова 401."""
    auth_client.post("/auth/login", json={"username": "admin", "password": "pw"})
    assert auth_client.get("/auth/me").status_code == 200

    resp = auth_client.post("/auth/logout")
    assert resp.status_code == 204
    assert auth_client.get("/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# API: RBAC — admin-only эндпоинт
# ---------------------------------------------------------------------------

def test_admin_only_forbidden_for_viewer(auth_client) -> None:
    """viewer на admin-only → 403."""
    auth_client.post("/auth/login", json={"username": "viewer", "password": "pw"})
    resp = auth_client.get("/admin-only")
    assert resp.status_code == 403


def test_admin_only_allowed_for_admin(auth_client) -> None:
    """admin на admin-only → 200."""
    auth_client.post("/auth/login", json={"username": "admin", "password": "pw"})
    resp = auth_client.get("/admin-only")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_admin_only_anonymous_401(auth_client) -> None:
    """Аноним на admin-only → 401 (не 403)."""
    resp = auth_client.get("/admin-only")
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/auth/me", "/admin-only"])
def test_invalid_cookie_treated_as_anonymous(auth_client, path) -> None:
    """Битый/неизвестный токен в cookie → 401 (как аноним)."""
    auth_client.cookies.set("cucumber_session", "garbage-token")
    resp = auth_client.get(path)
    assert resp.status_code == 401
