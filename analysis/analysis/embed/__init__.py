"""Фаза 4 — эмбеддинги и семантический поиск.

Публичный контракт (зафиксирован — НЕ менять сигнатуры): см. ``models``.
"""

from __future__ import annotations

from analysis.embed.models import EmbedStats, SearchHit

__all__ = ["EmbedStats", "SearchHit"]
