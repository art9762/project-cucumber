"""Селектор item'ов для инкрементального ресёрча (Фаза 3).

«Готов к ресёрчу» = item_analysis существует (классифицирован и проскорен),
но строки item_research ещё нет.  Фильтры важности: min_tier / min_coefficient
позволяют ограничиться наиболее ценными идеями.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.config import get_settings
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM, ItemResearchORM

# Маппинг tier → минимальный coefficient (включительно).
_TIER_FLOOR: dict[str, float] = {
    "S": 0.8,
    "A": 0.65,
    "B": 0.5,
    "C": 0.35,
    "D": 0.0,
}


async def select_unresearched_items(
    session: AsyncSession,
    *,
    limit: int | None = None,
    min_tier: str | None = None,
    min_coefficient: float | None = None,
) -> list[tuple[ItemReadORM, uuid.UUID | None]]:
    """Вернуть item'ы, классифицированные, но ещё не разобранные.

    Условие выборки: строка item_analysis есть, строки item_research нет.
    Порядок: item_analysis.coefficient DESC NULLS LAST, items.id — важные первыми.

    Args:
        session: Активная AsyncSession.
        limit: Максимальное количество строк; по умолчанию из Settings.analysis_batch_size.
        min_tier: Минимальный тир («не хуже»): S/A/B/C/D → порог coefficient.
        min_coefficient: Минимальный coefficient (включительно).

    Returns:
        Список пар ``(ItemReadORM, category_id)``.
    """
    effective_limit = limit if limit is not None else get_settings().analysis_batch_size

    # Вычислить реальный порог coefficient с учётом min_tier и min_coefficient.
    floor: float | None = None
    if min_tier is not None:
        tier_key = min_tier.strip().upper()
        tier_floor = _TIER_FLOOR.get(tier_key)
        if tier_floor is not None:
            floor = tier_floor

    if min_coefficient is not None:
        floor = max(floor, min_coefficient) if floor is not None else min_coefficient

    stmt = (
        select(ItemReadORM, ItemAnalysisORM.category_id)
        .join(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id)
        .outerjoin(ItemResearchORM, ItemResearchORM.item_id == ItemReadORM.id)
        .where(ItemResearchORM.id.is_(None))
        .order_by(
            ItemAnalysisORM.coefficient.desc().nulls_last(),
            ItemReadORM.id,
        )
        .limit(effective_limit)
    )

    if floor is not None:
        stmt = stmt.where(ItemAnalysisORM.coefficient >= floor)

    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]
