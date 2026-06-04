"""Единые pydantic-модели: Item (нормализованное), RawRecord (сырое), Job (задача)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    success = "success"
    failed = "failed"


class Item(BaseModel):
    """Нормализованная запись для поиска/аналитики. Дедуп по (source, external_id)."""

    source: str
    external_id: str
    title: str
    url: str
    author: str | None = None
    body: str | None = None
    score: int | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    fetched_at: datetime | None = None


class RawRecord(BaseModel):
    """Сырой ответ источника. `external_id` нужен, чтобы связать с Item при upsert."""

    source: str
    external_id: str
    payload: dict[str, Any]
    fetched_at: datetime | None = None


class JobStats(BaseModel):
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


class Job(BaseModel):
    """Состояние задачи сбора. Хранит per-source watermark (`since`) и `cursor` для resume."""

    id: UUID = Field(default_factory=uuid4)
    source: str
    status: JobState = JobState.queued
    since: datetime | None = None
    cursor: str | None = None
    stats: JobStats = Field(default_factory=JobStats)
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
