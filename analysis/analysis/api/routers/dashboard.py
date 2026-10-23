"""Dashboard counts computed in SQL without downloading bounded item lists."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import JSON, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.api.dashboard_schemas import DashboardStatsOut
from analysis.auth.dependencies import get_current_user
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM, ItemResearchORM, UserORM

router = APIRouter(tags=["dashboard"])
TIERS = ("S", "A", "B", "C", "D")


@router.get("/dashboard/stats", response_model=DashboardStatsOut)
async def get_dashboard_stats(
    session: Annotated[AsyncSession, Depends(get_analysis_session)],
    _user: Annotated[UserORM, Depends(get_current_user)],
) -> DashboardStatsOut:
    """Count every collected item, including items not yet classified or scored.

    A score exists when coefficient is non-null, matching GET /tierlist. The
    one-to-one result tables allow a single aggregate query and one DB snapshot.
    JSON null and SQL NULL both mean no competitor list.
    """
    scored = ItemAnalysisORM.coefficient.is_not(None)
    with_competitors = and_(
        ItemResearchORM.competitors.is_not(None),
        ItemResearchORM.competitors != JSON.NULL,
        ItemResearchORM.competitors != [],
    )
    stmt = (
        select(
            func.count(ItemReadORM.id).label("total_items"),
            func.count(case((scored, 1))).label("scored_items"),
            func.count(ItemResearchORM.id).label("researched_items"),
            func.count(case((with_competitors, 1))).label("with_competitors"),
            *(
                func.count(case((and_(scored, ItemAnalysisORM.tier == tier), 1))).label(tier)
                for tier in TIERS
            ),
        )
        .select_from(ItemReadORM)
        .outerjoin(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemReadORM.id)
        .outerjoin(ItemResearchORM, ItemResearchORM.item_id == ItemReadORM.id)
    )
    counts = (await session.execute(stmt)).one()._mapping
    return DashboardStatsOut(
        total_items=counts["total_items"],
        scored_items=counts["scored_items"],
        unscored_items=counts["total_items"] - counts["scored_items"],
        researched_items=counts["researched_items"],
        with_competitors=counts["with_competitors"],
        tier_counts={tier: counts[tier] for tier in TIERS},
    )
