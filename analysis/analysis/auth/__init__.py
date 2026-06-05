"""Пакет аутентификации/авторизации (Фаза 6): серверные сессии + RBAC."""

from __future__ import annotations

from analysis.auth.dependencies import (
    clear_session_cookie,
    get_cookie_name,
    get_current_user,
    get_optional_user,
    require_role,
    set_session_cookie,
)
from analysis.auth.hashing import hash_password, verify_password
from analysis.auth.sessions import create_session, resolve_session, revoke_session

__all__ = [
    "clear_session_cookie",
    "create_session",
    "get_cookie_name",
    "get_current_user",
    "get_optional_user",
    "hash_password",
    "require_role",
    "resolve_session",
    "revoke_session",
    "set_session_cookie",
    "verify_password",
]
