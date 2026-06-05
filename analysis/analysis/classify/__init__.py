"""Фаза 1 — классификация items по дереву категорий (Haiku через Trinity).

Публичный контракт фазы:

- :mod:`analysis.classify.models` — dataclass-контракт между слоями
  (``ClassificationResult``, ``CategoryNode``, ``ClassifyStats``).
- :mod:`analysis.classify.prompt` — построение промпта и парсинг ответа модели.
- :mod:`analysis.classify.categories` — репозиторий дерева категорий.
- :mod:`analysis.classify.classifier` — оркестратор прогона классификации.
"""

from __future__ import annotations

from analysis.classify.models import (
    CategoryNode,
    ClassificationResult,
    ClassifyStats,
)

__all__ = [
    "CategoryNode",
    "ClassificationResult",
    "ClassifyStats",
]
