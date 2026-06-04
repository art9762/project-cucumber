"""Реестр источников. Импорт модуля регистрирует все плагины v1."""

from __future__ import annotations

from find_engine.config import Settings, get_settings
from find_engine.core.source import register


def register_all(settings: Settings | None = None) -> None:
    """Инстанцировать и зарегистрировать все источники v1. Идемпотентно на уровне реестра."""
    settings = settings or get_settings()

    from find_engine.sources.arxiv import ArxivSource
    from find_engine.sources.github import GithubSource
    from find_engine.sources.hackernews import HackerNewsSource
    from find_engine.sources.reddit import RedditSource

    register(ArxivSource(settings))
    register(HackerNewsSource(settings))
    register(GithubSource(settings))
    register(RedditSource(settings))
