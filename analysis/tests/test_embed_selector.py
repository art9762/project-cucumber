"""Тесты селектора эмбеддинга (без Postgres, без сети).

Проверяет select_unembedded_items: возвращает только items без строки
item_embeddings, соблюдает порядок fetched_at/id, соблюдает limit.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from analysis.embed.selector import select_unembedded_items
from analysis.storage.orm import ItemEmbeddingORM, ItemReadORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _item(external_id: str, fetched_dt: datetime | None = None) -> ItemReadORM:
    """Создать тестовый ItemReadORM с уникальным external_id."""
    return ItemReadORM(
        source="test",
        external_id=external_id,
        title=f"Title {external_id}",
        url=f"https://example.com/{external_id}",
        tags=[],
        fetched_at=fetched_dt or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_only_unembedded(analysis_sessionmaker) -> None:
    """Items без item_embeddings возвращаются; с эмбеддингом — нет."""
    async with analysis_sessionmaker() as session:
        item_embedded = _item("emb1", datetime(2024, 1, 1, tzinfo=timezone.utc))
        item_bare = _item("bare1", datetime(2024, 1, 2, tzinfo=timezone.utc))
        session.add_all([item_embedded, item_bare])
        await session.commit()

        # Создаём эмбеддинг для первого item.
        emb = ItemEmbeddingORM(
            item_id=item_embedded.id,
            embedding=[1.0, 0.0, 0.0, 0.0],
            model="test-model",
            dim=4,
        )
        session.add(emb)
        await session.commit()

        result = await select_unembedded_items(session)

    ids = [it.id for it in result]
    assert item_bare.id in ids
    assert item_embedded.id not in ids


@pytest.mark.asyncio
async def test_order_fetched_at_then_id(analysis_sessionmaker) -> None:
    """Порядок: fetched_at ASC, id ASC."""
    dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dt2 = datetime(2024, 1, 2, tzinfo=timezone.utc)

    async with analysis_sessionmaker() as session:
        # item_b имеет более позднюю дату → должен идти вторым.
        item_a = _item("order_a", dt1)
        item_b = _item("order_b", dt2)
        session.add_all([item_b, item_a])  # Добавляем в обратном порядке.
        await session.commit()

        result = await select_unembedded_items(session)

    # Фильтруем только наши items (могут быть другие из предыдущих тестов, но
    # в отдельной SQLite :memory: сессии их нет).
    our_ids = {item_a.id, item_b.id}
    our_items = [it for it in result if it.id in our_ids]
    assert len(our_items) == 2
    assert our_items[0].id == item_a.id
    assert our_items[1].id == item_b.id


@pytest.mark.asyncio
async def test_limit_respected(analysis_sessionmaker) -> None:
    """limit=1 возвращает не более одного item."""
    async with analysis_sessionmaker() as session:
        items = [_item(f"lim{i}", datetime(2024, 1, i + 1, tzinfo=timezone.utc)) for i in range(3)]
        session.add_all(items)
        await session.commit()

        result = await select_unembedded_items(session, limit=1)

    assert len(result) == 1


@pytest.mark.asyncio
async def test_empty_table_returns_empty(analysis_sessionmaker) -> None:
    """Пустая таблица items → пустой список."""
    async with analysis_sessionmaker() as session:
        result = await select_unembedded_items(session)
    assert result == []


@pytest.mark.asyncio
async def test_all_embedded_returns_empty(analysis_sessionmaker) -> None:
    """Все items имеют эмбеддинг → пустой список."""
    async with analysis_sessionmaker() as session:
        item = _item("all_emb")
        session.add(item)
        await session.commit()

        emb = ItemEmbeddingORM(
            item_id=item.id,
            embedding=[0.1, 0.2, 0.3, 0.4],
            model="test-model",
            dim=4,
        )
        session.add(emb)
        await session.commit()

        result = await select_unembedded_items(session)

    ids = [it.id for it in result]
    assert item.id not in ids
