"""Фаза 3 — веб-ресёрч и поиск конкурентов.

Публичный контракт (зафиксирован — НЕ менять сигнатуры): см. ``models``.
"""

from __future__ import annotations

from analysis.research.models import (
    Competitor,
    ResearchResult,
    ResearchStats,
)

__all__ = [
    "Competitor",
    "ResearchResult",
    "ResearchStats",
]
