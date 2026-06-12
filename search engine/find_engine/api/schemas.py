"""HTTP request/response-схемы API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from find_engine.core.models import JobStats


class CreateJobRequest(BaseModel):
    source: str


class JobResponse(BaseModel):
    id: UUID
    source: str
    status: str
    since: datetime | None = None
    cursor: str | None = None
    stats: JobStats
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class HealthResponse(BaseModel):
    status: str
    sources: list[str]


class ScheduleUpdateRequest(BaseModel):
    cron: str


class ScheduleResponse(BaseModel):
    schedules: dict[str, str]
