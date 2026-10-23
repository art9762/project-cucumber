"""Aggregate dashboard statistics over the complete collected corpus."""

from pydantic import BaseModel


class DashboardStatsOut(BaseModel):
    total_items: int
    scored_items: int
    unscored_items: int
    researched_items: int
    with_competitors: int
    tier_counts: dict[str, int]
