"""Pydantic-схемы для прокси-роутера сборщика (Фаза collect)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CollectStats(BaseModel):
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


class CollectJobOut(BaseModel):
    """Зеркало JobResponse коллектора."""

    id: str
    source: str
    status: str
    since: str | None = None
    cursor: str | None = None
    stats: CollectStats = CollectStats()
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SourcesOut(BaseModel):
    sources: list[str]


class ScheduleOut(BaseModel):
    schedules: dict[str, str]


class CreateCollectJob(BaseModel):
    source: str


class ScheduleUpdateRequest(BaseModel):
    cron: str
