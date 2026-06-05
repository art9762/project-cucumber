"""Tests for analysis.embed.search (SQLite dialect / Python cosine path).

All tests run on in-memory SQLite via the ``analysis_sessionmaker`` fixture
from conftest.py.  pgvector operators are never invoked here.

Seed vectors are intentionally short (dim=4) — SQLite stores them as JSON
lists, which is fine for the Python cosine fallback.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from analysis.embed.models import SearchHit
from analysis.embed.search import _cosine_distance, find_competitors, search_by_text, search_by_vector
from analysis.storage.orm import (
    CategoryORM,
    ItemAnalysisORM,
    ItemEmbeddingORM,
    ItemReadORM,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _item(external_id: str) -> ItemReadORM:
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=_utcnow(),
    )


def _embedding(item: ItemReadORM, vec: list[float]) -> ItemEmbeddingORM:
    return ItemEmbeddingORM(
        item_id=item.id,
        embedding=vec,
        model="test-model",
        dim=len(vec),
    )


def _normalize(v: list[float]) -> list[float]:
    """Return unit-length vector."""
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# Unit vectors used throughout the tests (dim=4).
# VEC_A is the query direction; VEC_B is very close; VEC_C is orthogonal.
VEC_A = _normalize([1.0, 0.0, 0.0, 0.0])   # query direction
VEC_B = _normalize([1.0, 0.1, 0.0, 0.0])   # very close to A
VEC_C = _normalize([0.0, 0.0, 1.0, 0.0])   # orthogonal to A (distance ≈ 1)
VEC_D = _normalize([0.0, 1.0, 0.0, 0.0])   # semi-orthogonal


# ---------------------------------------------------------------------------
# Pure cosine helper tests
# ---------------------------------------------------------------------------

class TestCosineDistance:
    def test_identical_vectors_zero(self) -> None:
        assert _cosine_distance(VEC_A, VEC_A) == pytest.approx(0.0, abs=1e-9)

    def test_orthogonal_vectors_one(self) -> None:
        assert _cosine_distance(VEC_A, VEC_C) == pytest.approx(1.0, abs=1e-9)

    def test_zero_vector_returns_one(self) -> None:
        assert _cosine_distance([0.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_symmetry(self) -> None:
        assert _cosine_distance(VEC_B, VEC_C) == pytest.approx(_cosine_distance(VEC_C, VEC_B))


# ---------------------------------------------------------------------------
# search_by_vector — ordering and similarity
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_by_vector_nearest_first(analysis_sessionmaker) -> None:
    """Nearest item (smallest cosine distance) appears first."""
    async with analysis_sessionmaker() as session:
        item_b = _item("b")
        item_c = _item("c")
        session.add_all([item_b, item_c])
        await session.flush()

        session.add_all([
            _embedding(item_b, VEC_B),  # closer to VEC_A
            _embedding(item_c, VEC_C),  # farther
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10)

    assert len(hits) == 2
    assert hits[0].distance <= hits[1].distance
    assert hits[0].title == "Title b"


@pytest.mark.asyncio
async def test_search_by_vector_similarity_is_one_minus_distance(analysis_sessionmaker) -> None:
    """similarity == 1 - distance for every returned hit."""
    async with analysis_sessionmaker() as session:
        item_a = _item("sim_a")
        item_b = _item("sim_b")
        session.add_all([item_a, item_b])
        await session.flush()
        session.add_all([_embedding(item_a, VEC_A), _embedding(item_b, VEC_B)])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10)

    assert len(hits) >= 1
    for hit in hits:
        assert hit.similarity == pytest.approx(1.0 - hit.distance, abs=1e-9)


@pytest.mark.asyncio
async def test_search_by_vector_limit(analysis_sessionmaker) -> None:
    """limit=1 returns exactly one result even when more exist."""
    async with analysis_sessionmaker() as session:
        items = [_item(f"lim{i}") for i in range(4)]
        session.add_all(items)
        await session.flush()
        vecs = [VEC_A, VEC_B, VEC_C, VEC_D]
        session.add_all([_embedding(items[i], vecs[i]) for i in range(4)])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=1)

    assert len(hits) == 1


@pytest.mark.asyncio
async def test_search_by_vector_exclude_item_id(analysis_sessionmaker) -> None:
    """exclude_item_id removes that item from results."""
    async with analysis_sessionmaker() as session:
        item_x = _item("excl_x")
        item_y = _item("excl_y")
        session.add_all([item_x, item_y])
        await session.flush()
        excl_id = item_x.id
        session.add_all([
            _embedding(item_x, VEC_A),
            _embedding(item_y, VEC_B),
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10, exclude_item_id=excl_id)

    ids = [h.item_id for h in hits]
    assert str(excl_id) not in ids
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_search_by_vector_empty_table(analysis_sessionmaker) -> None:
    """No embeddings → empty result."""
    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10)
    assert hits == []


# ---------------------------------------------------------------------------
# search_by_vector — tier/coefficient/category_id from item_analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_by_vector_includes_analysis_fields(analysis_sessionmaker) -> None:
    """SearchHit carries tier, coefficient, category_id from item_analysis."""
    async with analysis_sessionmaker() as session:
        cat = CategoryORM(slug="ai", title="AI", approved=True)
        item = _item("ana1")
        session.add_all([cat, item])
        await session.flush()

        ia = ItemAnalysisORM(
            item_id=item.id,
            category_id=cat.id,
            tier="A",
            coefficient=0.71,
        )
        session.add_all([ia, _embedding(item, VEC_A)])
        await session.commit()
        expected_cat_id = str(cat.id)

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10)

    assert len(hits) == 1
    hit = hits[0]
    assert hit.tier == "A"
    assert hit.coefficient == pytest.approx(0.71)
    assert hit.category_id == expected_cat_id


@pytest.mark.asyncio
async def test_search_by_vector_no_analysis_fields_are_none(analysis_sessionmaker) -> None:
    """Item without item_analysis row → tier/coefficient/category_id are None."""
    async with analysis_sessionmaker() as session:
        item = _item("noana")
        session.add(item)
        await session.flush()
        session.add(_embedding(item, VEC_A))
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await search_by_vector(session, VEC_A, limit=10)

    assert len(hits) == 1
    assert hits[0].tier is None
    assert hits[0].coefficient is None
    assert hits[0].category_id is None


# ---------------------------------------------------------------------------
# find_competitors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_competitors_returns_other_items(analysis_sessionmaker) -> None:
    """find_competitors for item_b should return item_c (not item_b itself)."""
    async with analysis_sessionmaker() as session:
        item_b = _item("comp_b")
        item_c = _item("comp_c")
        session.add_all([item_b, item_c])
        await session.flush()
        b_id = item_b.id
        session.add_all([
            _embedding(item_b, VEC_B),
            _embedding(item_c, VEC_C),
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await find_competitors(session, b_id, limit=10)

    returned_ids = [h.item_id for h in hits]
    assert str(b_id) not in returned_ids
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_find_competitors_no_embedding_returns_empty(analysis_sessionmaker) -> None:
    """Item with no embedding row → find_competitors returns []."""
    async with analysis_sessionmaker() as session:
        item = _item("noembedding")
        session.add(item)
        await session.commit()
        item_id = item.id

    async with analysis_sessionmaker() as session:
        hits = await find_competitors(session, item_id, limit=10)

    assert hits == []


@pytest.mark.asyncio
async def test_find_competitors_ordering(analysis_sessionmaker) -> None:
    """Competitors returned nearest-first."""
    async with analysis_sessionmaker() as session:
        # item_src has VEC_A; item_close has VEC_B (very close); item_far has VEC_C.
        src = _item("src")
        close = _item("close")
        far = _item("far")
        session.add_all([src, close, far])
        await session.flush()
        src_id = src.id
        session.add_all([
            _embedding(src, VEC_A),
            _embedding(close, VEC_B),
            _embedding(far, VEC_C),
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        hits = await find_competitors(session, src_id, limit=10)

    assert len(hits) == 2
    assert hits[0].distance <= hits[1].distance
    assert hits[0].title == "Title close"


# ---------------------------------------------------------------------------
# search_by_text — fake encoder stub
# ---------------------------------------------------------------------------

class _FakeEncoder:
    """Deterministic encoder stub: always returns the same fixed vector."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    def encode(self, text: str) -> list[float]:  # noqa: ARG002
        return self._vec


@pytest.mark.asyncio
async def test_search_by_text_uses_encoder_vector(analysis_sessionmaker) -> None:
    """search_by_text(encoder) returns same results as search_by_vector with encoded vec."""
    async with analysis_sessionmaker() as session:
        item_b = _item("txt_b")
        item_c = _item("txt_c")
        session.add_all([item_b, item_c])
        await session.flush()
        session.add_all([
            _embedding(item_b, VEC_B),
            _embedding(item_c, VEC_C),
        ])
        await session.commit()

    encoder = _FakeEncoder(VEC_A)

    async with analysis_sessionmaker() as session:
        hits_text = await search_by_text(session, encoder, "any query", limit=10)

    async with analysis_sessionmaker() as session:
        hits_vec = await search_by_vector(session, VEC_A, limit=10)

    assert [h.item_id for h in hits_text] == [h.item_id for h in hits_vec]


@pytest.mark.asyncio
async def test_search_by_text_limit(analysis_sessionmaker) -> None:
    """search_by_text respects limit parameter."""
    async with analysis_sessionmaker() as session:
        items = [_item(f"tl{i}") for i in range(3)]
        session.add_all(items)
        await session.flush()
        vecs = [VEC_A, VEC_B, VEC_C]
        session.add_all([_embedding(items[i], vecs[i]) for i in range(3)])
        await session.commit()

    encoder = _FakeEncoder(VEC_A)
    async with analysis_sessionmaker() as session:
        hits = await search_by_text(session, encoder, "q", limit=1)

    assert len(hits) == 1


# ---------------------------------------------------------------------------
# SearchHit contract
# ---------------------------------------------------------------------------

def test_search_hit_is_frozen() -> None:
    """SearchHit is a frozen dataclass; mutation raises AttributeError."""
    hit = SearchHit(
        item_id="abc",
        title="T",
        url="http://x",
        distance=0.1,
        similarity=0.9,
    )
    with pytest.raises((AttributeError, TypeError)):
        hit.distance = 0.5  # type: ignore[misc]
