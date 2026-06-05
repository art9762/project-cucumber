"""GET /tierlist, GET /items/{item_id}/score, POST /score — роутер скоринга (Фаза 2)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.api.score_schemas import ItemScoreOut, ScoreRunOut, TierItemOut
from analysis.storage.db import get_analysis_session, get_analysis_sessionmaker
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM

router = APIRouter(tags=["scores"])


@router.get("/tierlist", response_model=list[TierItemOut])
async def get_tierlist(
    tier: Optional[str] = Query(default=None),
    category_id: Optional[uuid.UUID] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_analysis_session),
) -> list[TierItemOut]:
    """Вернуть тирлист items, отсортированный по coefficient убывающе."""
    stmt = (
        select(ItemReadORM, ItemAnalysisORM)
        .join(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id)
        .where(ItemAnalysisORM.coefficient.is_not(None))
        .order_by(ItemAnalysisORM.coefficient.desc())
    )
    if tier is not None:
        stmt = stmt.where(ItemAnalysisORM.tier == tier)
    if category_id is not None:
        stmt = stmt.where(ItemAnalysisORM.category_id == category_id)
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    rows = result.all()
    return [
        TierItemOut(
            item_id=str(item.id),
            title=item.title,
            url=item.url,
            category_id=str(analysis.category_id) if analysis.category_id is not None else None,
            tier=analysis.tier,
            coefficient=analysis.coefficient,
            scores=dict(analysis.scores) if analysis.scores is not None else None,
        )
        for item, analysis in rows
    ]


@router.get("/items/{item_id}/score", response_model=ItemScoreOut)
async def get_item_score(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_analysis_session),
) -> ItemScoreOut:
    """Вернуть результат скоринга для item_id. 404, если строка не найдена."""
    stmt = (
        select(ItemReadORM, ItemAnalysisORM)
        .join(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id)
        .where(ItemAnalysisORM.item_id == item_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item score not found")
    item, analysis = row
    return ItemScoreOut(
        item_id=str(item.id),
        title=item.title,
        url=item.url,
        category_id=str(analysis.category_id) if analysis.category_id is not None else None,
        tier=analysis.tier,
        coefficient=analysis.coefficient,
        scores=dict(analysis.scores) if analysis.scores is not None else None,
        model_used=analysis.model_used,
    )


@router.post("/score", response_model=ScoreRunOut)
async def run_score(
    limit: Optional[int] = Query(default=None, ge=1),
) -> ScoreRunOut:
    """Запустить прогон скоринга новых items. Возвращает статистику прогона."""
    from analysis.score.scorer import run_scoring  # ленивый импорт
    from analysis.trinity import get_trinity_client  # ленивый импорт

    stats = await run_scoring(
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=limit,
    )
    return ScoreRunOut(
        seen=stats.seen,
        scored=stats.scored,
        escalated=stats.escalated,
        failed=stats.failed,
        tier_counts=stats.tier_counts,
        errors=stats.errors,
    )
