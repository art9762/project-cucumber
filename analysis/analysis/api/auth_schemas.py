"""Pydantic-схемы для API аутентификации (Фаза 6).

Контракт согласован с фронтендом:
  POST /auth/login  {username, password}
  GET  /auth/me     -> {username, role}
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginIn(BaseModel):
    """Тело запроса логина."""

    username: str
    password: str


class UserOut(BaseModel):
    """Публичное представление пользователя для /auth/login и /auth/me."""

    username: str
    role: str
