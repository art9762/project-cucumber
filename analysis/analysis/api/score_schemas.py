"""Pydantic-схемы для API скоринга (Фаза 2).

Не изменять api/schemas.py — этот файл дополняет его для маршрутов скоринга.
"""

from __future__ import annotations

from pydantic import BaseModel


class TierItemOut(BaseModel):
    """Элемент тирлиста с коэффициентом и тиром."""

    item_id: str
    title: str
    url: str
    category_id: str | None
    tier: str | None
    coefficient: float | None
    scores: dict[str, float] | None


class ItemScoreOut(BaseModel):
    """Полный результат скоринга одного item, включая model_used."""

    item_id: str
    title: str
    url: str
    category_id: str | None
    tier: str | None
    coefficient: float | None
    scores: dict[str, float] | None
    model_used: str | None


class ScoreRunOut(BaseModel):
    """Результат прогона скоринга (по полям ScoreStats)."""

    seen: int
    scored: int
    escalated: int
    failed: int
    tier_counts: dict[str, int]
    errors: list[str]
