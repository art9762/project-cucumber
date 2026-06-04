"""GET /health — живость сервиса анализа: БД и Trinity."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysis.api.schemas import HealthResponse
from analysis.storage.db import get_analysis_sessionmaker

router = APIRouter(tags=["health"])


async def _check_db(sessionmaker: async_sessionmaker[AsyncSession]) -> bool:
    """Выполнить SELECT 1 через переданный sessionmaker; вернуть True при успехе."""
    try:
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Проверить доступность БД и наличие токена Trinity.

    Всегда возвращает 200; состояние отражается в теле ответа.
    """
    from analysis.trinity import get_trinity_client  # ленивый импорт

    db_ok = await _check_db(get_analysis_sessionmaker())
    trinity_configured = get_trinity_client().is_configured
    status = "ok" if db_ok else "degraded"
    return HealthResponse(status=status, database=db_ok, trinity_configured=trinity_configured)
