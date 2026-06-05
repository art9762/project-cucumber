"""Контракт Фазы 4 (embeddings + поиск) — зафиксирован, НЕ менять сигнатуры.

Локальная модель (fastembed, CPU) векторизует items; векторы лежат в
``item_embeddings`` (pgvector). Поверх — семантический поиск и поиск конкурентов
по косинусной близости.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EmbedStats:
    """Статистика прогона эмбеддинга (как ClassifyStats/ScoreStats)."""

    seen: int = 0
    embedded: int = 0
    failed: int = 0
    model: str | None = None
    dim: int | None = None
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "seen": self.seen,
            "embedded": self.embedded,
            "failed": self.failed,
            "model": self.model,
            "dim": self.dim,
            "errors": self.errors,
        }


@dataclass(frozen=True)
class SearchHit:
    """Результат семантического поиска: item + дистанция/похожесть.

    ``distance`` — косинусная дистанция (0 = идентично, 2 = противоположно).
    ``similarity`` = 1 - distance (удобнее читать; больше = ближе).
    """

    item_id: str
    title: str
    url: str
    distance: float
    similarity: float
    tier: str | None = None
    coefficient: float | None = None
    category_id: str | None = None
