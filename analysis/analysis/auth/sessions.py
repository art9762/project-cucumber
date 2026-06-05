"""Серверные сессии: опаковый токен в БД (secrets.token_urlsafe), без JWT.

create_session  → выдать новый токен и записать строку sessions.
resolve_session → токен → активный UserORM (проверка срока и is_active) | None.
revoke_session  → удалить строку сессии (logout).
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.storage.orm import SessionORM, UserORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(
    session: AsyncSession, user_id: uuid.UUID, ttl_hours: int
) -> str:
    """Создать сессию для user_id со сроком ttl_hours; вернуть опаковый токен."""
    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=ttl_hours)
    session.add(SessionORM(token=token, user_id=user_id, expires_at=expires_at))
    await session.commit()
    return token


async def resolve_session(session: AsyncSession, token: str) -> UserORM | None:
    """Вернуть активного пользователя по токену либо None.

    None, если: токена нет, сессия истекла, пользователь не найден или неактивен.
    """
    if not token:
        return None
    row = await session.execute(
        select(SessionORM).where(SessionORM.token == token)
    )
    sess = row.scalar_one_or_none()
    if sess is None:
        return None

    expires_at = sess.expires_at
    if expires_at.tzinfo is None:  # SQLite отдаёт naive datetime
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _utcnow():
        return None

    user_row = await session.execute(
        select(UserORM).where(UserORM.id == sess.user_id)
    )
    user = user_row.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def revoke_session(session: AsyncSession, token: str) -> None:
    """Удалить строку сессии по токену (logout). Молча игнорирует отсутствие."""
    if not token:
        return
    await session.execute(delete(SessionORM).where(SessionORM.token == token))
    await session.commit()
