"""GET /health — живость + список зарегистрированных источников."""

from __future__ import annotations

from fastapi import APIRouter

from find_engine.api.schemas import HealthResponse
from find_engine.core.source import available_sources

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", sources=available_sources())
