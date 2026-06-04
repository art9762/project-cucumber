"""HTTP request/response-схемы API модуля анализа."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Ответ эндпоинта /health."""

    status: str
    database: bool
    trinity_configured: bool
