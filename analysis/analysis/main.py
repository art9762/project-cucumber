"""Точка входа FastAPI: регистрирует роутеры модуля анализа."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analysis.api.routers import auth, categories, collect, health, research, scores, search
from analysis.config import get_settings


def create_app() -> FastAPI:
    """Собрать и вернуть экземпляр FastAPI."""
    app = FastAPI(title="analysis", version="0.1.0")

    # CORS только если задан явный список origin'ов (cookie-сессии требуют
    # allow_credentials=True, что несовместимо с wildcard). См. config.cors_origins.
    origins = get_settings().cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(categories.router)
    app.include_router(scores.router)
    app.include_router(research.router)
    app.include_router(search.router)
    app.include_router(collect.router)
    return app


app = create_app()
