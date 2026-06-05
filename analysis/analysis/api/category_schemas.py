"""Pydantic-схемы для API категорий (Фаза 1).

Не изменять api/schemas.py — этот файл дополняет его для маршрутов категорий.
"""

from __future__ import annotations

from pydantic import BaseModel


class CategoryOut(BaseModel):
    """Плоское представление узла дерева категорий."""

    id: str
    slug: str
    title: str
    parent_id: str | None
    approved: bool


class CategoryTreeNode(BaseModel):
    """Рекурсивный узел дерева с вложенными потомками."""

    id: str
    slug: str
    title: str
    approved: bool
    children: list[CategoryTreeNode] = []


CategoryTreeNode.model_rebuild()


class ClassifyRunOut(BaseModel):
    """Результат прогона классификации (по полям ClassifyStats)."""

    seen: int
    classified: int
    suggested: int
    failed: int
    errors: list[str]


class ApproveResponse(BaseModel):
    """Ответ на approve-запрос."""

    ok: bool
    id: str
    approved: bool


class RejectResponse(BaseModel):
    """Ответ на reject-запрос."""

    ok: bool
    id: str
