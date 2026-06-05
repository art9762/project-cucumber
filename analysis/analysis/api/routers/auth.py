"""POST /auth/login, POST /auth/logout, GET /auth/me — роутер аутентификации (Фаза 6).

Модель: серверные сессии с HttpOnly-cookie (НЕ JWT). Контракт совпадает с тем,
к которому кодируется React-клиент.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.api.auth_schemas import LoginIn, UserOut
from analysis.auth.dependencies import (
    clear_session_cookie,
    get_current_user,
    set_session_cookie,
)
from analysis.auth.hashing import verify_password
from analysis.auth.sessions import create_session, revoke_session
from analysis.config import get_settings
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import UserORM

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginIn,
    response: Response,
    session: AsyncSession = Depends(get_analysis_session),
) -> UserOut:
    """Проверить логин/пароль, создать сессию, выставить cookie. 401 при ошибке."""
    row = await session.execute(
        select(UserORM).where(UserORM.username == body.username)
    )
    user = row.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = await create_session(
        session, user.id, get_settings().session_ttl_hours
    )
    set_session_cookie(response, token)
    return UserOut(username=user.username, role=user.role)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_analysis_session),
) -> Response:
    """Отозвать сессию (если есть) и очистить cookie. 204 в любом случае."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        await revoke_session(session, token)
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: UserORM = Depends(get_current_user)) -> UserOut:
    """Текущий пользователь. 401, если не аутентифицирован."""
    return UserOut(username=user.username, role=user.role)
