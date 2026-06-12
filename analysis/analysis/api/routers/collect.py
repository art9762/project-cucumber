"""Auth gateway для внутреннего collector-сервиса.

Все маршруты /collect/* проксируют запросы в collector (http://collector:8114)
по внутренней docker-сети. Collector не имеет собственной аутентификации и не
выставлен наружу — вся защита здесь через require_role("admin").
"""

from __future__ import annotations

import re
import uuid as _uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from analysis.api.collect_schemas import (
    CollectJobOut,
    CreateCollectJob,
    ScheduleOut,
    ScheduleUpdateRequest,
    SourcesOut,
)
from analysis.auth.dependencies import require_role
from analysis.config import get_settings

router = APIRouter(prefix="/collect", tags=["collect"])

_TIMEOUT = 30.0
_SOURCE_RE = re.compile(r"^[a-z0-9_-]+$")


def _collector_url(path: str) -> str:
    base = get_settings().collector_base_url.rstrip("/")
    return f"{base}{path}"


def _propagate_error(e: httpx.HTTPStatusError) -> None:
    try:
        body = e.response.json()
        detail = body["detail"] if isinstance(body, dict) and "detail" in body else body
    except Exception:
        detail = e.response.text or e.response.reason_phrase
    raise HTTPException(status_code=e.response.status_code, detail=detail)


def _unavailable() -> None:
    raise HTTPException(status_code=502, detail="collector unavailable")


@router.get("/sources", response_model=SourcesOut)
async def get_sources(_user=Depends(require_role("admin"))) -> SourcesOut:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(_collector_url("/health"))
            r.raise_for_status()
            return SourcesOut(sources=r.json().get("sources", []))
    except httpx.HTTPStatusError as e:
        _propagate_error(e)
    except httpx.HTTPError:
        _unavailable()


@router.post("/jobs", response_model=CollectJobOut, status_code=202)
async def create_job(
    body: CreateCollectJob,
    response: Response,
    _user=Depends(require_role("admin")),
) -> CollectJobOut:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(_collector_url("/jobs"), json=body.model_dump())
            r.raise_for_status()
            response.status_code = r.status_code
            return CollectJobOut(**r.json())
    except httpx.HTTPStatusError as e:
        _propagate_error(e)
    except httpx.HTTPError:
        _unavailable()


@router.get("/jobs/{job_id}", response_model=CollectJobOut)
async def get_job(job_id: _uuid.UUID, _user=Depends(require_role("admin"))) -> CollectJobOut:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(_collector_url(f"/jobs/{job_id}"))
            r.raise_for_status()
            return CollectJobOut(**r.json())
    except httpx.HTTPStatusError as e:
        _propagate_error(e)
    except httpx.HTTPError:
        _unavailable()


@router.get("/schedule", response_model=ScheduleOut)
async def get_schedule(_user=Depends(require_role("admin"))) -> ScheduleOut:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(_collector_url("/schedule"))
            r.raise_for_status()
            return ScheduleOut(**r.json())
    except httpx.HTTPStatusError as e:
        _propagate_error(e)
    except httpx.HTTPError:
        _unavailable()


@router.put("/schedule/{source}", response_model=ScheduleOut)
async def update_schedule(
    source: str,
    body: ScheduleUpdateRequest,
    _user=Depends(require_role("admin")),
) -> ScheduleOut:
    if not _SOURCE_RE.match(source):
        raise HTTPException(status_code=404, detail="unknown source")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.put(
                _collector_url(f"/schedule/{source}"),
                json=body.model_dump(),
            )
            r.raise_for_status()
            return ScheduleOut(**r.json())
    except httpx.HTTPStatusError as e:
        _propagate_error(e)
    except httpx.HTTPError:
        _unavailable()
