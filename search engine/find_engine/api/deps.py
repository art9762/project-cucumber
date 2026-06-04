"""Зависимости API: orchestrator из app.state."""

from __future__ import annotations

from fastapi import Request

from find_engine.core.orchestrator import Orchestrator


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator
