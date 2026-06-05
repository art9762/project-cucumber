"""GET /items/{item_id}/research, GET /research, POST /research — роутер ресёрча (Фаза 3)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.api.research_schemas import CompetitorOut, ItemResearchOut, ResearchRunOut
from analysis.storage.db import get_analysis_session, get_analysis_sessionmaker
from analysis.storage.orm import ItemReadORM, ItemResearchORM

router = APIRouter(tags=["research"])


def _competitors_from_json(raw: list | None) -> list[CompetitorOut]:
    """Map JSONB list of dicts → list[CompetitorOut] defensively."""
    if not raw:
        return []
    result: list[CompetitorOut] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        result.append(
            CompetitorOut(
                name=str(name),
                url=entry.get("url") or None,
                note=entry.get("note") or None,
            )
        )
    return result


def _build_item_research_out(item: ItemReadORM, research: ItemResearchORM) -> ItemResearchOut:
    return ItemResearchOut(
        item_id=str(item.id),
        title=item.title,
        url=item.url,
        summary=research.summary,
        competitors=_competitors_from_json(research.competitors),
        sources=list(research.sources) if research.sources else [],
        maturity_signal=research.maturity_signal,
        potential_signal=research.potential_signal,
        model_used=research.model_used,
    )


@router.get("/items/{item_id}/research", response_model=ItemResearchOut)
async def get_item_research(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_analysis_session),
) -> ItemResearchOut:
    """Вернуть результат ресёрча для item_id. 404, если строка не найдена."""
    stmt = (
        select(ItemReadORM, ItemResearchORM)
        .join(ItemResearchORM, ItemResearchORM.item_id == ItemReadORM.id)
        .where(ItemResearchORM.item_id == item_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Item research not found")
    item, research = row
    return _build_item_research_out(item, research)


@router.get("/research", response_model=list[ItemResearchOut])
async def list_research(
    has_competitors: Optional[bool] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1),
    session: AsyncSession = Depends(get_analysis_session),
) -> list[ItemResearchOut]:
    """Вернуть список ресёрч-результатов. Опциональный фильтр по наличию конкурентов."""
    stmt = (
        select(ItemReadORM, ItemResearchORM)
        .join(ItemResearchORM, ItemResearchORM.item_id == ItemReadORM.id)
        .order_by(ItemResearchORM.researched_at.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    rows = result.all()

    items_out = [_build_item_research_out(item, research) for item, research in rows]

    if has_competitors is True:
        items_out = [r for r in items_out if r.competitors]
    elif has_competitors is False:
        items_out = [r for r in items_out if not r.competitors]

    return items_out


@router.post("/research", response_model=ResearchRunOut)
async def run_research_endpoint(
    limit: Optional[int] = Query(default=None, ge=1),
    min_tier: Optional[str] = Query(default=None),
    min_coefficient: Optional[float] = Query(default=None, ge=0.0, le=1.0),
) -> ResearchRunOut:
    """Запустить прогон веб-ресёрча новых items. Возвращает статистику прогона."""
    from analysis.research.researcher import run_research  # ленивый импорт
    from analysis.trinity import get_trinity_client  # ленивый импорт

    stats = await run_research(
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=limit,
        min_tier=min_tier,
        min_coefficient=min_coefficient,
    )
    return ResearchRunOut(
        seen=stats.seen,
        researched=stats.researched,
        competitors_found=stats.competitors_found,
        failed=stats.failed,
        errors=stats.errors,
    )
