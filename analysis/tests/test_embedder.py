"""Тесты оркестратора эмбеддинга (без Postgres, без сети, без fastembed).

Использует общую фикстуру ``analysis_sessionmaker`` из conftest.py.
Encoder заглушается фейковым объектом с детерминированным encode_batch.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from analysis.embed.embedder import run_embedding
from analysis.storage.orm import AnalysisRunORM, ItemEmbeddingORM, ItemReadORM


# ---------------------------------------------------------------------------
# Фейковый Encoder
# ---------------------------------------------------------------------------

class _FakeEncoder:
    """Stub encoder: не грузит fastembed, возвращает детерминированные векторы."""

    model_name: str = "fake-model"
    dim: int = 4  # маленькая размерность — SQLite хранит JSON

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Возвращает вектор длиной 4, где каждый элемент = float(len(text))."""
        return [[float(len(t))] * self.dim for t in texts]


class _FakeEncoderRaisingOnFirst:
    """Stub encoder: всегда возвращает корректные векторы (сбой провоцируется через БД)."""

    model_name: str = "fake-model-raises"
    dim: int = 4

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * self.dim for t in texts]


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _item(external_id: str, fetched_dt: datetime | None = None) -> ItemReadORM:
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
async def test_happy_path(analysis_sessionmaker) -> None:
    """После успешного прогона item_embeddings записан, stats корректны."""
    async with analysis_sessionmaker() as session:
        item = _item("emb_h1")
        session.add(item)
        await session.commit()
        item_id = item.id

    encoder = _FakeEncoder()
    stats = await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    assert stats.seen == 1
    assert stats.embedded == 1
    assert stats.failed == 0
    assert stats.model == "fake-model"
    assert stats.dim == 4
    assert stats.errors == []

    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemEmbeddingORM).where(ItemEmbeddingORM.item_id == item_id)
        )
        emb = result.scalars().first()
        assert emb is not None
        assert emb.model == "fake-model"
        assert emb.dim == 4
        # embedding сохранён как список float.
        assert isinstance(emb.embedding, list)
        assert len(emb.embedding) == 4
        assert all(isinstance(v, float) for v in emb.embedding)


@pytest.mark.asyncio
async def test_idempotency_second_run_sees_zero(analysis_sessionmaker) -> None:
    """Второй прогон не трогает уже эмбеддированный item: stats.seen == 0."""
    async with analysis_sessionmaker() as session:
        item = _item("emb_i1")
        session.add(item)
        await session.commit()

    encoder = _FakeEncoder()
    await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    stats2 = await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    assert stats2.seen == 0
    assert stats2.embedded == 0


@pytest.mark.asyncio
async def test_per_item_failure_does_not_abort_run(analysis_sessionmaker, monkeypatch) -> None:
    """Инъекция сбоя на первом item → failed==1, embedded==1, прогон не обрывается."""
    import analysis.embed.embedder as embedder_mod

    original_embed_item = embedder_mod._embed_item
    call_count = 0

    async def _failing_embed_item(**kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            kwargs["stats"].failed += 1
            kwargs["stats"].errors.append(f"{kwargs['item'].id}: injected failure")
            return
        await original_embed_item(**kwargs)

    monkeypatch.setattr(embedder_mod, "_embed_item", _failing_embed_item)

    async with analysis_sessionmaker() as session:
        item_a = _item("emb_fail_a", datetime(2024, 1, 1, 1, tzinfo=timezone.utc))
        item_b = _item("emb_fail_b", datetime(2024, 1, 1, 2, tzinfo=timezone.utc))
        session.add_all([item_a, item_b])
        await session.commit()
        item_b_id = item_b.id

    encoder = _FakeEncoder()
    stats = await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    assert stats.seen == 2
    assert stats.failed == 1
    assert stats.embedded == 1
    assert len(stats.errors) == 1

    # item_b должен быть эмбеддирован успешно.
    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(ItemEmbeddingORM).where(ItemEmbeddingORM.item_id == item_b_id)
        )
        emb = result.scalars().first()
        assert emb is not None, "Второй item должен быть эмбеддирован"


@pytest.mark.asyncio
async def test_analysis_runs_kind_embed_status_success(analysis_sessionmaker) -> None:
    """После прогона в analysis_runs есть строка kind='embed', status='success'."""
    async with analysis_sessionmaker() as session:
        item = _item("emb_r1")
        session.add(item)
        await session.commit()

    encoder = _FakeEncoder()
    await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    async with analysis_sessionmaker() as session:
        result = await session.execute(
            select(AnalysisRunORM).where(AnalysisRunORM.kind == "embed")
        )
        run = result.scalars().first()
        assert run is not None
        assert run.kind == "embed"
        assert run.status == "success"
        assert run.started_at is not None
        assert run.finished_at is not None
        assert run.stats is not None
        assert run.stats.get("embedded") == 1


@pytest.mark.asyncio
async def test_empty_table_no_error(analysis_sessionmaker) -> None:
    """Если нет items — прогон завершается успешно с seen=0."""
    encoder = _FakeEncoder()
    stats = await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    assert stats.seen == 0
    assert stats.embedded == 0
    assert stats.failed == 0


@pytest.mark.asyncio
async def test_multiple_items_all_embedded(analysis_sessionmaker) -> None:
    """Несколько items — все получают корректный эмбеддинг."""
    async with analysis_sessionmaker() as session:
        items = [_item(f"multi{i}", datetime(2024, 1, i + 1, tzinfo=timezone.utc)) for i in range(3)]
        session.add_all(items)
        await session.commit()
        item_ids = [it.id for it in items]

    encoder = _FakeEncoder()
    stats = await run_embedding(
        read_sessionmaker=analysis_sessionmaker,
        analysis_sessionmaker=analysis_sessionmaker,
        encoder=encoder,
        limit=100,
    )

    assert stats.seen == 3
    assert stats.embedded == 3
    assert stats.failed == 0

    async with analysis_sessionmaker() as session:
        for iid in item_ids:
            result = await session.execute(
                select(ItemEmbeddingORM).where(ItemEmbeddingORM.item_id == iid)
            )
            emb = result.scalars().first()
            assert emb is not None
            assert isinstance(emb.embedding, list)
            assert len(emb.embedding) == 4
