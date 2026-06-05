"""Semantic search over item embeddings (Phase 4).

Dialect-aware: on Postgres uses pgvector ``<=>`` operator via SQLAlchemy
``text()``.  On SQLite (unit tests) falls back to Python-side cosine.
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.embed.models import SearchHit
from analysis.storage.orm import ItemAnalysisORM, ItemEmbeddingORM, ItemReadORM


# ---------------------------------------------------------------------------
# Internal cosine helper — defined here to avoid importing encoder.py
# (which would transitively pull fastembed when not installed).
# ---------------------------------------------------------------------------

def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine distance 1 - (a·b)/(|a||b|).  Zero vector → 1.0."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def _vector_literal(vec: list[float]) -> str:
    """pgvector-совместимый литерал ``[f1,f2,…]``.

    Каждый элемент приводится к python ``float`` — это важно, т.к. энкодер
    (fastembed) может отдавать ``numpy.float32``, чей ``repr`` (``np.float32(…)``)
    pgvector распарсить не может.
    """
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


# ---------------------------------------------------------------------------
# Dialect detection helper
# ---------------------------------------------------------------------------

def _dialect_name(session: AsyncSession) -> str:
    """Return dialect name ('postgresql' | 'sqlite' | …)."""
    bind = session.get_bind()
    return bind.dialect.name  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def search_by_vector(
    session: AsyncSession,
    query_vec: list[float],
    *,
    limit: int = 10,
    exclude_item_id: uuid.UUID | None = None,
) -> list[SearchHit]:
    """Return top-K nearest items by cosine distance to *query_vec*.

    Handles both Postgres (pgvector ``<=>`` operator) and SQLite (Python
    cosine fallback for unit tests).  ``exclude_item_id`` is filtered out
    before ranking so that ``find_competitors`` can reuse this function.
    """
    dialect = _dialect_name(session)

    if dialect == "postgresql":
        return await _search_postgres(session, query_vec, limit=limit, exclude_item_id=exclude_item_id)
    return await _search_sqlite(session, query_vec, limit=limit, exclude_item_id=exclude_item_id)


async def search_by_text(
    session: AsyncSession,
    encoder: Any,
    query: str,
    *,
    limit: int = 10,
) -> list[SearchHit]:
    """Encode *query* with *encoder* then delegate to search_by_vector.

    *encoder* is typed ``Any`` to avoid importing the Encoder class (and
    transitively fastembed) at module load time.  It must expose
    ``encode(text: str) -> list[float]``.
    """
    vec: list[float] = encoder.encode(query)
    return await search_by_vector(session, vec, limit=limit)


async def find_competitors(
    session: AsyncSession,
    item_id: uuid.UUID,
    *,
    limit: int = 10,
) -> list[SearchHit]:
    """Return nearest items to *item_id*, excluding the item itself.

    If the item has no embedding row, returns an empty list.
    """
    stmt = select(ItemEmbeddingORM).where(ItemEmbeddingORM.item_id == item_id)
    result = await session.execute(stmt)
    emb_row = result.scalars().first()

    if emb_row is None or emb_row.embedding is None:
        return []

    vec: list[float] = list(emb_row.embedding)
    return await search_by_vector(session, vec, limit=limit, exclude_item_id=item_id)


# ---------------------------------------------------------------------------
# Dialect-specific implementations
# ---------------------------------------------------------------------------

async def _search_postgres(
    session: AsyncSession,
    query_vec: list[float],
    *,
    limit: int,
    exclude_item_id: uuid.UUID | None,
) -> list[SearchHit]:
    """Postgres path: ORDER BY embedding <=> :vec using pgvector operator."""
    exclude_clause = ""
    params: dict[str, Any] = {"vec": _vector_literal(query_vec), "lim": limit}

    if exclude_item_id is not None:
        exclude_clause = "AND ie.item_id != :excl"
        params["excl"] = str(exclude_item_id)

    sql = text(
        f"""
        SELECT
            ie.item_id                  AS item_id,
            it.title                    AS title,
            it.url                      AS url,
            (ie.embedding <=> CAST(:vec AS vector))  AS distance,
            ia.tier                     AS tier,
            ia.coefficient              AS coefficient,
            ia.category_id              AS category_id
        FROM item_embeddings ie
        JOIN items it ON it.id = ie.item_id
        LEFT JOIN item_analysis ia ON ia.item_id = ie.item_id
        WHERE ie.embedding IS NOT NULL
        {exclude_clause}
        ORDER BY ie.embedding <=> CAST(:vec AS vector)
        LIMIT :lim
        """
    )

    rows = (await session.execute(sql, params)).mappings().all()
    return [_row_to_hit(r, float(r["distance"])) for r in rows]


async def _search_sqlite(
    session: AsyncSession,
    query_vec: list[float],
    *,
    limit: int,
    exclude_item_id: uuid.UUID | None,
) -> list[SearchHit]:
    """SQLite path: fetch all embeddings, compute cosine in Python, sort."""
    stmt = (
        select(
            ItemEmbeddingORM,
            ItemReadORM,
            ItemAnalysisORM,
        )
        .join(ItemReadORM, ItemReadORM.id == ItemEmbeddingORM.item_id)
        .outerjoin(ItemAnalysisORM, ItemAnalysisORM.item_id == ItemEmbeddingORM.item_id)
        .where(ItemEmbeddingORM.embedding.isnot(None))
    )

    if exclude_item_id is not None:
        stmt = stmt.where(ItemEmbeddingORM.item_id != exclude_item_id)

    rows = (await session.execute(stmt)).all()

    scored: list[tuple[float, Any, Any, Any]] = []
    for emb_orm, item_orm, analysis_orm in rows:
        vec = list(emb_orm.embedding)
        dist = _cosine_distance(query_vec, vec)
        scored.append((dist, emb_orm, item_orm, analysis_orm))

    scored.sort(key=lambda t: t[0])
    top = scored[:limit]

    hits: list[SearchHit] = []
    for dist, _emb, item_orm, analysis_orm in top:
        hits.append(
            SearchHit(
                item_id=str(item_orm.id),
                title=item_orm.title,
                url=item_orm.url,
                distance=dist,
                similarity=1.0 - dist,
                tier=analysis_orm.tier if analysis_orm else None,
                coefficient=analysis_orm.coefficient if analysis_orm else None,
                category_id=str(analysis_orm.category_id) if (analysis_orm and analysis_orm.category_id) else None,
            )
        )
    return hits


def _row_to_hit(row: Any, distance: float) -> SearchHit:
    """Convert a Postgres result mapping row to SearchHit."""
    cat_id = row["category_id"]
    return SearchHit(
        item_id=str(row["item_id"]),
        title=row["title"],
        url=row["url"],
        distance=distance,
        similarity=1.0 - distance,
        tier=row["tier"],
        coefficient=row["coefficient"],
        category_id=str(cat_id) if cat_id is not None else None,
    )
