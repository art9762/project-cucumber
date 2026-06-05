"""FastAPI-зависимости аутентификации/авторизации (Фаза 6).

- get_current_user      — читает cookie, резолвит сессию → UserORM, иначе 401.
- get_optional_user     — то же, но None вместо 401 (для публичных-с-апгрейдом).
- require_role("admin") — фабрика зависимости, 403 при недостаточной роли.

Параметры cookie (имя, HttpOnly, Secure, SameSite) централизованы здесь, чтобы
роутер логина/логаута и фронтенд опирались на единый контракт.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.auth.sessions import resolve_session
from analysis.config import get_settings
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import UserORM

# Иерархия ролей: чем больше число, тем больше прав.
_ROLE_RANK = {"viewer": 1, "admin": 2}


def get_cookie_name() -> str:
    """Имя session-cookie (из конфига; по умолчанию 'cucumber_session')."""
    return get_settings().session_cookie_name


def set_session_cookie(response: Response, token: str) -> None:
    """Выставить session-cookie: HttpOnly всегда, Secure из конфига, SameSite=Lax."""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Удалить session-cookie (logout). Флаги должны совпадать с установкой."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


async def get_optional_user(
    request: Request,
    session: AsyncSession = Depends(get_analysis_session),
) -> UserORM | None:
    """Вернуть текущего пользователя по cookie либо None (без 401)."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        return None
    return await resolve_session(session, token)


async def get_current_user(
    user: UserORM | None = Depends(get_optional_user),
) -> UserORM:
    """Вернуть текущего пользователя или 401, если не аутентифицирован."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


def require_role(role: str):
    """Фабрика зависимости: требует роль не ниже `role`, иначе 403."""
    required_rank = _ROLE_RANK.get(role, 0)

    async def _dependency(
        user: UserORM = Depends(get_current_user),
    ) -> UserORM:
        if _ROLE_RANK.get(user.role, 0) < required_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{role}'",
            )
        return user

    return _dependency
