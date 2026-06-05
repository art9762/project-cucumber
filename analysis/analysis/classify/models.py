"""Контракт данных Фазы 1 (классификация).

Чистые dataclass'ы без зависимостей на ORM/SDK — общий язык между слоями:
парсер промпта, репозиторий категорий и оркестратор обмениваются этими типами.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CategoryNode:
    """Узел дерева категорий (снимок из БД, без ORM-привязки).

    Attributes:
        id: UUID узла.
        slug: Машинный идентификатор (уникален, ASCII-kebab).
        title: Человекочитаемое название.
        parent_id: UUID родителя или None для верхнего уровня.
        approved: Утверждён ли узел вручную (гибридная таксономия).
    """

    id: uuid.UUID
    slug: str
    title: str
    parent_id: uuid.UUID | None
    approved: bool


@dataclass(frozen=True)
class ClassificationResult:
    """Результат классификации одного item, разобранный из ответа модели.

    Модель обязана выбрать существующую категорию верхнего уровня
    (``category_slug`` — один из seed-slug'ов). Опционально предлагает
    подкатегорию (``suggested_subcategory_*``) — она создаётся неутверждённой
    (``approved=False``) и ждёт ручного утверждения.

    Attributes:
        category_slug: Slug выбранной существующей категории (обязательно).
        confidence: Уверенность модели 0.0–1.0.
        suggested_subcategory_slug: Предлагаемый slug новой подкатегории
            (kebab-case, ASCII) или None.
        suggested_subcategory_title: Человекочитаемое название подкатегории
            или None. Согласован с ``suggested_subcategory_slug``: оба None
            либо оба заданы.
    """

    category_slug: str
    confidence: float
    suggested_subcategory_slug: str | None = None
    suggested_subcategory_title: str | None = None

    @property
    def has_suggestion(self) -> bool:
        """True, если модель предложила новую подкатегорию."""
        return self.suggested_subcategory_slug is not None


@dataclass
class ClassifyStats:
    """Агрегированная статистика прогона классификации (пишется в analysis_runs.stats)."""

    seen: int = 0
    classified: int = 0
    suggested: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        """JSON-совместимый словарь для analysis_runs.stats."""
        return {
            "seen": self.seen,
            "classified": self.classified,
            "suggested": self.suggested,
            "failed": self.failed,
            "errors": self.errors,
        }
