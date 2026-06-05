"""Селектор item'ов для инкрементального скоринга (Фаза 2).

«Готов к скорингу» = item_analysis существует (category_id задан после Фазы 1),
но coefficient ещё не выставлен (NULL).  Т.е. item прошёл классификацию,
но ещё не прошёл скоринг.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.config import get_settings
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM


async def select_unscored_items(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> list[tuple[ItemReadORM, uuid.UUID | None]]:
    """Вернуть item'ы, классифицированные, но ещё не проскоренные.

    Условие выборки: строка item_analysis есть, category_id задан,
    coefficient IS NULL.  Порядок: fetched_at ASC, id ASC — детерминированный.

    Args:
        session: Активная AsyncSession.
        limit: Максимальное количество строк; по умолчанию берётся из
            ``Settings.analysis_batch_size``.

    Returns:
        Список пар ``(ItemReadORM, category_id)``.
    """
    effective_limit = limit if limit is not None else get_settings().analysis_batch_size

    stmt = (
        select(ItemReadORM, ItemAnalysisORM.category_id)
        .join(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id)
        .where(
            ItemAnalysisORM.category_id.is_not(None),
            ItemAnalysisORM.coefficient.is_(None),
        )
        .order_by(ItemReadORM.fetched_at, ItemReadORM.id)
        .limit(effective_limit)
    )

    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]
