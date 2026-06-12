"""GET /schedule, PUT /schedule/{source} — cron schedule management.

No auth on this router: collector is internal; the analysis gateway guards it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from find_engine.api.deps import get_scheduler
from find_engine.api.schemas import ScheduleResponse, ScheduleUpdateRequest
from find_engine.core.scheduler import Scheduler
from find_engine.core.source import available_sources
from find_engine.storage.db import get_sessionmaker
from find_engine.storage.repository import Repository

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get("", response_model=ScheduleResponse)
async def get_schedule(scheduler: Scheduler = Depends(get_scheduler)) -> ScheduleResponse:
    active = scheduler.current_schedules()
    schedules = {src: active.get(src, "") for src in available_sources()}
    return ScheduleResponse(schedules=schedules)


@router.put("/{source}", response_model=ScheduleResponse)
async def update_schedule(
    source: str,
    body: ScheduleUpdateRequest,
    scheduler: Scheduler = Depends(get_scheduler),
) -> ScheduleResponse:
    if source not in available_sources():
        raise HTTPException(status_code=404, detail=f"Unknown source {source!r}")

    try:
        scheduler.reschedule(source, body.cron)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with get_sessionmaker()() as session:
        repo = Repository(session)
        if body.cron.strip():
            await repo.upsert_schedule(source, body.cron)
        else:
            await repo.delete_schedule(source)
        await session.commit()

    active = scheduler.current_schedules()
    schedules = {src: active.get(src, "") for src in available_sources()}
    return ScheduleResponse(schedules=schedules)
