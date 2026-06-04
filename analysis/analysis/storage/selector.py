"""Селектор «новых» items для инкрементальной обработки.

«Новый» item = item без строки в ``item_analysis`` (LEFT JOIN … WHERE ia.id IS NULL).
UUID-идентификаторы не монотонны, поэтому курсор по id не применяется — только JOIN.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import outerjoin

from analysis.config import get_settings
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM


async def select_new_items(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> list[ItemReadORM]:
    """Возвращает items, ещё не прошедшие анализ.

    Порядок: ``fetched_at ASC``, затем ``id ASC`` — детерминированный и
    стабильный при пакетной обработке.

    Args:
        session: Активная AsyncSession.
        limit: Максимальное количество строк. По умолчанию берётся из
            ``Settings.analysis_batch_size``.

    Returns:
        Список :class:`ItemReadORM`-объектов без соответствующей записи в
        ``item_analysis``.
    """
    effective_limit = limit if limit is not None else get_settings().analysis_batch_size

    stmt = (
        select(ItemReadORM)
        .select_from(outerjoin(ItemReadORM, ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id))
        .where(ItemAnalysisORM.id.is_(None))
        .order_by(ItemReadORM.fetched_at, ItemReadORM.id)
        .limit(effective_limit)
    )

    result = await session.execute(stmt)
    return list(result.scalars().all())
