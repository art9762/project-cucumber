"""POST /search, GET /items/{id}/competitors, POST /embed — роутер поиска (Фаза 4)."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.api.search_schemas import EmbedRunOut, SearchHitOut, SearchQueryIn
from analysis.embed.models import SearchHit
from analysis.storage.db import (
    get_analysis_session,
    get_analysis_sessionmaker,
    get_read_sessionmaker,
)

router = APIRouter(tags=["search"])

# ---------------------------------------------------------------------------
# Ленивый синглтон Encoder — НЕ конструировать при импорте модуля.
# ---------------------------------------------------------------------------

_encoder: object | None = None


def _get_encoder() -> object:
    """Вернуть (или создать при первом вызове) синглтон Encoder."""
    global _encoder
    if _encoder is None:
        from analysis.embed.encoder import Encoder  # noqa: PLC0415

        _encoder = Encoder()
    return _encoder


# ---------------------------------------------------------------------------
# Вспомогательная функция маппинга SearchHit → SearchHitOut
# ---------------------------------------------------------------------------


def _hit_to_out(hit: SearchHit) -> SearchHitOut:
    return SearchHitOut(
        item_id=hit.item_id,
        title=hit.title,
        url=hit.url,
        distance=hit.distance,
        similarity=hit.similarity,
        tier=hit.tier,
        coefficient=hit.coefficient,
        category_id=hit.category_id,
    )


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------


@router.post("/search", response_model=list[SearchHitOut])
async def search_items(
    body: SearchQueryIn,
    session: AsyncSession = Depends(get_analysis_session),
) -> list[SearchHitOut]:
    """Семантический поиск: текст → top-K ближайших items по косинусу."""
    from analysis.embed.search import search_by_text  # noqa: PLC0415

    encoder = _get_encoder()
    hits = await search_by_text(session, encoder, body.query, limit=body.limit)
    return [_hit_to_out(h) for h in hits]


@router.get("/items/{item_id}/competitors", response_model=list[SearchHitOut])
async def get_competitors(
    item_id: uuid.UUID,
    limit: Optional[int] = Query(default=10, ge=1),
    session: AsyncSession = Depends(get_analysis_session),
) -> list[SearchHitOut]:
    """Поиск конкурентов: похожие items по косинусу к вектору item_id."""
    from analysis.embed.search import find_competitors  # noqa: PLC0415

    hits = await find_competitors(session, item_id, limit=limit or 10)
    return [_hit_to_out(h) for h in hits]


@router.post("/embed", response_model=EmbedRunOut)
async def run_embed(
    limit: Optional[int] = Query(default=None, ge=1),
) -> EmbedRunOut:
    """Запустить прогон эмбеддинга невекторизованных items. Возвращает статистику."""
    from analysis.embed.embedder import run_embedding  # noqa: PLC0415

    encoder = _get_encoder()
    stats = await run_embedding(
        read_sessionmaker=get_read_sessionmaker(),
        analysis_sessionmaker=get_analysis_sessionmaker(),
        encoder=encoder,
        limit=limit,
    )
    return EmbedRunOut(
        seen=stats.seen,
        embedded=stats.embedded,
        failed=stats.failed,
        model=stats.model,
        dim=stats.dim,
        errors=stats.errors,
    )
