"""Pydantic-схемы для API ресёрча (Фаза 3).

Не изменять api/schemas.py — этот файл дополняет его для маршрутов ресёрча.
"""

from __future__ import annotations

from pydantic import BaseModel


class CompetitorOut(BaseModel):
    """Найденный конкурент/похожее решение."""

    name: str
    url: str | None = None
    note: str | None = None


class ItemResearchOut(BaseModel):
    """Полный результат веб-ресёрча одного item."""

    item_id: str
    title: str
    url: str
    summary: str | None
    competitors: list[CompetitorOut]
    sources: list[str]
    maturity_signal: float | None
    potential_signal: float | None
    model_used: str | None


class ResearchRunOut(BaseModel):
    """Результат прогона ресёрча (по полям ResearchStats)."""

    seen: int
    researched: int
    competitors_found: int
    failed: int
    errors: list[str]
