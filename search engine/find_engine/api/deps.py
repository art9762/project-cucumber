"""Зависимости API: orchestrator и scheduler из app.state."""

from __future__ import annotations

from fastapi import Request

from find_engine.core.orchestrator import Orchestrator
from find_engine.core.scheduler import Scheduler


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


def get_scheduler(request: Request) -> Scheduler:
    return request.app.state.scheduler
