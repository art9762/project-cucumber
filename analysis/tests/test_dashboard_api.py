"""Regression tests for complete-corpus dashboard counters."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import null

from analysis.auth.dependencies import get_current_user
from analysis.main import create_app
from analysis.storage.db import get_analysis_session
from analysis.storage.orm import ItemAnalysisORM, ItemReadORM, ItemResearchORM, UserORM


def _client(sessionmaker, *, role="viewer") -> TestClient:
    app = create_app()

    async def session_override():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_analysis_session] = session_override
    if role is not None:
        app.dependency_overrides[get_current_user] = lambda: UserORM(
            username="tester", password_hash="unused", role=role, is_active=True
        )
    return TestClient(app)


def _item(index: int) -> ItemReadORM:
    return ItemReadORM(
        id=uuid.uuid4(),
        source="github",
        external_id=str(index),
        title=f"Project {index}",
        url=f"https://example.com/{index}",
        tags=[],
    )


@pytest.mark.parametrize("role", ["viewer", "admin"])
def test_empty_corpus_returns_zero_counts_for_both_roles(analysis_sessionmaker, role):
    response = _client(analysis_sessionmaker, role=role).get("/dashboard/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total_items": 0,
        "scored_items": 0,
        "unscored_items": 0,
        "researched_items": 0,
        "with_competitors": 0,
        "tier_counts": {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0},
    }


def test_stats_require_authentication(analysis_sessionmaker):
    response = _client(analysis_sessionmaker, role=None).get("/dashboard/stats")
    assert response.status_code == 401


async def test_stats_include_unprocessed_items_and_all_research(analysis_sessionmaker):
    items = [_item(index) for index in range(9)]
    async with analysis_sessionmaker() as session:
        session.add_all(items)
        await session.flush()
        for item, tier in zip(items, ("S", "A", "B", "C", "D")):
            session.add(ItemAnalysisORM(item_id=item.id, tier=tier, coefficient=0.0))
        # Classified but unscored must count alongside completely untouched items.
        session.add(ItemAnalysisORM(item_id=items[5].id, tier="S", coefficient=None))
        for index, competitors in (
            (0, [{"name": "One"}, {"name": "Two"}]),
            (1, []),
            (2, None),
            (7, [{"name": "Three"}]),
            (8, null()),
        ):
            session.add(ItemResearchORM(
                item_id=items[index].id, competitors=competitors, sources=[]
            ))
        await session.commit()

    response = _client(analysis_sessionmaker).get("/dashboard/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total_items": 9,
        "scored_items": 5,
        "unscored_items": 4,
        "researched_items": 5,
        "with_competitors": 2,
        "tier_counts": {"S": 1, "A": 1, "B": 1, "C": 1, "D": 1},
    }


async def test_stats_are_not_truncated_at_one_thousand_items(analysis_sessionmaker):
    items = [_item(index) for index in range(1008)]
    async with analysis_sessionmaker() as session:
        session.add_all(items)
        await session.flush()
        for index, item in enumerate(items[:1005]):
            session.add(ItemAnalysisORM(item_id=item.id, tier="S", coefficient=0.9))
            session.add(ItemResearchORM(
                item_id=item.id,
                competitors=[{"name": "Competitor"}] if index % 2 == 0 else [],
                sources=[],
            ))
        await session.commit()

    response = _client(analysis_sessionmaker).get("/dashboard/stats")
    assert response.status_code == 200
    assert response.json() == {
        "total_items": 1008,
        "scored_items": 1005,
        "unscored_items": 3,
        "researched_items": 1005,
        "with_competitors": 503,
        "tier_counts": {"S": 1005, "A": 0, "B": 0, "C": 0, "D": 0},
    }
