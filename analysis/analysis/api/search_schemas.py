"""Pydantic-схемы для API поиска и эмбеддинга (Фаза 4).

Дополняет search_schemas для маршрутов /search, /embed, /items/{id}/competitors.
"""

from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    """Результат семантического поиска: item + дистанция/похожесть."""

    item_id: str
    title: str
    url: str
    distance: float
    similarity: float
    tier: str | None
    coefficient: float | None
    category_id: str | None


class EmbedRunOut(BaseModel):
    """Результат прогона эмбеддинга (по полям EmbedStats)."""

    seen: int
    embedded: int
    failed: int
    model: str | None
    dim: int | None
    errors: list[str]


class SearchQueryIn(BaseModel):
    """Тело запроса POST /search — текст и количество результатов."""

    query: str
    limit: int = 10
