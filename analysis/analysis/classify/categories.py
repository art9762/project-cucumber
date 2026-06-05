"""Репозиторий дерева категорий (Фаза 1).

Все функции работают с analysis-сессией и возвращают чистые ``CategoryNode``
dataclass'ы — ORM-объекты не пересекают границу модуля.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.classify.models import CategoryNode
from analysis.storage.orm import CategoryORM


# ---------------------------------------------------------------------------
# Внутренний конвертер ORM → dataclass
# ---------------------------------------------------------------------------

def _to_node(row: CategoryORM) -> CategoryNode:
    """Конвертировать ORM-строку в неизменяемый CategoryNode."""
    return CategoryNode(
        id=row.id,
        slug=row.slug,
        title=row.title,
        parent_id=row.parent_id,
        approved=row.approved,
    )


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------

async def load_category_tree(session: AsyncSession) -> list[CategoryNode]:
    """Все категории (любой approved) как список CategoryNode."""
    result = await session.execute(select(CategoryORM))
    return [_to_node(r) for r in result.scalars()]


async def load_approved_top_level(session: AsyncSession) -> list[CategoryNode]:
    """Только approved=True и parent_id IS NULL — кандидаты для промпта."""
    stmt = select(CategoryORM).where(
        CategoryORM.approved.is_(True),
        CategoryORM.parent_id.is_(None),
    )
    result = await session.execute(stmt)
    return [_to_node(r) for r in result.scalars()]


async def get_by_slug(session: AsyncSession, slug: str) -> CategoryNode | None:
    """Категория по slug или None."""
    stmt = select(CategoryORM).where(CategoryORM.slug == slug)
    result = await session.execute(stmt)
    row = result.scalars().first()
    return _to_node(row) if row is not None else None


async def ensure_subcategory(
    session: AsyncSession,
    *,
    parent_slug: str,
    slug: str,
    title: str,
) -> CategoryNode:
    """Идемпотентно вернуть/создать подкатегорию под parent_slug.

    Новая запись создаётся с approved=False. Если slug уже существует —
    возвращается существующий узел без изменений. Бросает ValueError, если
    parent_slug не найден. НЕ коммитит — это делает вызывающий.
    """
    parent = await get_by_slug(session, parent_slug)
    if parent is None:
        raise ValueError(f"Родительская категория не найдена: {parent_slug!r}")

    existing = await get_by_slug(session, slug)
    if existing is not None:
        return existing

    new_row = CategoryORM(
        parent_id=parent.id,
        slug=slug,
        title=title,
        approved=False,
    )
    session.add(new_row)
    await session.flush()
    return _to_node(new_row)


async def list_pending(session: AsyncSession) -> list[CategoryNode]:
    """Неутверждённые категории (approved=False) — очередь на утверждение."""
    stmt = select(CategoryORM).where(CategoryORM.approved.is_(False))
    result = await session.execute(stmt)
    return [_to_node(r) for r in result.scalars()]


async def set_approved(
    session: AsyncSession,
    category_id: uuid.UUID,
    approved: bool,
) -> CategoryNode | None:
    """Установить флаг approved. Вернуть обновлённый узел или None, если не найден.

    НЕ коммитит — это делает вызывающий.
    """
    stmt = select(CategoryORM).where(CategoryORM.id == category_id)
    result = await session.execute(stmt)
    row = result.scalars().first()
    if row is None:
        return None
    row.approved = approved
    await session.flush()
    return _to_node(row)


async def delete_category(session: AsyncSession, category_id: uuid.UUID) -> bool:
    """Удалить узел. True если удалён, False если не найден. НЕ коммитит."""
    stmt = select(CategoryORM).where(CategoryORM.id == category_id)
    result = await session.execute(stmt)
    row = result.scalars().first()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
