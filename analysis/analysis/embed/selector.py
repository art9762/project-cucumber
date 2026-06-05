"""Селектор item'ов для инкрементального эмбеддинга (Фаза 4).

«Готов к эмбеддингу» = нет строки item_embeddings (LEFT JOIN → id IS NULL).
Эмбеддим ВСЕ items, независимо от статуса классификации/скоринга — вектор полезен
сам по себе.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.config import get_settings
from analysis.storage.orm import ItemEmbeddingORM, ItemReadORM


async def select_unembedded_items(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> list[ItemReadORM]:
    """Вернуть items без строки item_embeddings.

    Условие: LEFT JOIN item_embeddings по item_id; фильтр ItemEmbeddingORM.id IS NULL.
    Порядок: fetched_at ASC, id ASC — детерминированный.

    Args:
        session: Активная AsyncSession (analysis-сессия).
        limit: Максимальное число строк; по умолчанию из Settings.analysis_batch_size.

    Returns:
        Список :class:`ItemReadORM` без эмбеддинга.
    """
    effective_limit = limit if limit is not None else get_settings().analysis_batch_size

    stmt = (
        select(ItemReadORM)
        .outerjoin(ItemEmbeddingORM, ItemEmbeddingORM.item_id == ItemReadORM.id)
        .where(ItemEmbeddingORM.id.is_(None))
        .order_by(ItemReadORM.fetched_at, ItemReadORM.id)
        .limit(effective_limit)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())
