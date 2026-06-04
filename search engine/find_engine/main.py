"""Точка входа FastAPI: регистрирует источники, поднимает orchestrator и scheduler."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from find_engine.api.routers import health, jobs
from find_engine.config import get_settings
from find_engine.core.orchestrator import Orchestrator
from find_engine.core.scheduler import Scheduler
from find_engine.sources import register_all
from find_engine.storage.db import get_sessionmaker

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    register_all(settings)

    orchestrator = Orchestrator(get_sessionmaker())
    app.state.orchestrator = orchestrator

    scheduler = Scheduler(orchestrator, settings)
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="find-engine", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(jobs.router)
    return app


app = create_app()
