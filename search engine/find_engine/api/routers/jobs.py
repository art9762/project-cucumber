"""POST /jobs — запустить сбор по источнику; GET /jobs/{id} — статус и stats."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from find_engine.api.deps import get_orchestrator
from find_engine.api.schemas import CreateJobRequest, JobResponse
from find_engine.core.orchestrator import Orchestrator
from find_engine.core.source import available_sources, get_source
from find_engine.storage.db import get_sessionmaker
from find_engine.storage.repository import Repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=202)
async def create_job(
    req: CreateJobRequest,
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> JobResponse:
    try:
        source = get_source(req.source)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source {req.source!r}. Available: {available_sources()}",
        )

    job_id = await orchestrator.create_job(source)

    async def _run() -> None:
        try:
            await orchestrator.run_job(job_id, source)
        except Exception:  # noqa: BLE001 — статус уже зафиксирован в job
            logger.exception("Background job %s failed", job_id)

    asyncio.create_task(_run())
    return await _job_response(job_id)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID) -> JobResponse:
    return await _job_response(job_id)


async def _job_response(job_id: UUID) -> JobResponse:
    async with get_sessionmaker()() as session:
        job = await Repository(session).get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job.model_dump())
