"""Точка входа FastAPI: регистрирует роутеры модуля анализа."""

from __future__ import annotations

from fastapi import FastAPI

from analysis.api.routers import categories, health, scores


def create_app() -> FastAPI:
    """Собрать и вернуть экземпляр FastAPI."""
    app = FastAPI(title="analysis", version="0.1.0")
    app.include_router(health.router)
    app.include_router(categories.router)
    app.include_router(scores.router)
    return app


app = create_app()
