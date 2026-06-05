"""Оркестратор эмбеддинга (Фаза 4).

Запускает батчевую векторизацию items локальной моделью (fastembed, CPU),
сохраняет векторы в item_embeddings и фиксирует прогон в analysis_runs.

Изоляция ошибок: каждый item обрабатывается внутри SAVEPOINT (begin_nested).
На исключении SAVEPOINT откатывается — уже успешно эмбеддированные items
остаются в транзакции и комитятся в конце.

Примечание: encode_batch выполняется ВНЕ SAVEPOINT (CPU-bound, без БД-операций).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysis.embed.models import EmbedStats
from analysis.embed.selector import select_unembedded_items
from analysis.storage.orm import AnalysisRunORM, ItemEmbeddingORM, ItemReadORM


def _utcnow() -> datetime:
    """Вернуть текущее UTC-время."""
    return datetime.now(timezone.utc)


async def _embed_item(
    *,
    item: ItemReadORM,
    vec: list[float],
    analysis_session: AsyncSession,
    model_name: str,
    dim: int,
    stats: EmbedStats,
) -> None:
    """Сохранить вектор одного item внутри SAVEPOINT.

    При любом исключении SAVEPOINT откатывается, stats.failed инкрементируется.
    """
    try:
        async with analysis_session.begin_nested():
            analysis_session.add(
                ItemEmbeddingORM(
                    item_id=item.id,
                    embedding=vec,
                    model=model_name,
                    dim=dim,
                )
            )
        stats.embedded += 1
    except Exception as exc:  # noqa: BLE001
        stats.failed += 1
        stats.errors.append(f"{item.id}: {exc}")


async def run_embedding(
    *,
    read_sessionmaker: async_sessionmaker[AsyncSession],
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    encoder: object,
    limit: int | None = None,
) -> EmbedStats:
    """Полный прогон эмбеддинга одного батча невекторизованных items.

    1. Фиксирует analysis_runs-строку (kind='embed', status='running').
    2. Читает items без строки item_embeddings через analysis-сессию.
    3. Строит тексты для эмбеддинга; вызывает encoder.encode_batch (ВНЕ savepoint).
    4. Для каждого (item, vec) внутри begin_nested(): INSERT ItemEmbeddingORM.
    5. Обновляет analysis_runs-строку (status='success'/'failed', stats, finished_at).

    Args:
        read_sessionmaker: Принимается для единообразия сигнатур; items читаются
            analysis-сессией (обе таблицы на одной БД, как в scorer.py).
        analysis_sessionmaker: Async sessionmaker для чтения items и записи эмбеддингов.
        encoder: Объект с .encode_batch(texts), .model_name, .dim.
        limit: Максимальное число items в батче; None — из Settings.

    Returns:
        :class:`EmbedStats` с агрегированной статистикой прогона.
    """
    stats = EmbedStats()
    run_id = None

    async with analysis_sessionmaker() as analysis_session:
        # Шаг 1: зафиксировать запуск немедленно.
        run = AnalysisRunORM(kind="embed", status="running", started_at=_utcnow())
        analysis_session.add(run)
        await analysis_session.flush()
        run_id = run.id
        await analysis_session.commit()

        try:
            # Шаг 2: прочитать items без эмбеддинга.
            items = await select_unembedded_items(analysis_session, limit=limit)
            stats.seen = len(items)

            # Шаг 3: построить тексты и вызвать encode_batch (CPU-bound, вне savepoint).
            if items:
                # Ленивый импорт чтобы не тянуть fastembed при импорте модуля.
                from analysis.embed.encoder import build_embed_text  # noqa: PLC0415

                texts = [build_embed_text(it) for it in items]
                vecs: list[list[float]] = encoder.encode_batch(texts)  # type: ignore[attr-defined]

                model_name: str = encoder.model_name  # type: ignore[attr-defined]
                dim: int = encoder.dim  # type: ignore[attr-defined]
                stats.model = model_name
                stats.dim = dim

                # Шаг 4: сохранить каждый вектор внутри SAVEPOINT.
                for item, vec in zip(items, vecs):
                    await _embed_item(
                        item=item,
                        vec=vec,
                        analysis_session=analysis_session,
                        model_name=model_name,
                        dim=dim,
                        stats=stats,
                    )
            else:
                stats.model = encoder.model_name  # type: ignore[attr-defined]
                stats.dim = encoder.dim  # type: ignore[attr-defined]

            final_status = "success"
        except Exception as exc:  # noqa: BLE001
            final_status = "failed"
            stats.errors.append(f"fatal: {exc}")

        # Шаг 5: зафиксировать итог прогона.
        await analysis_session.execute(
            update(AnalysisRunORM)
            .where(AnalysisRunORM.id == run_id)
            .values(status=final_status, finished_at=_utcnow(), stats=stats.as_dict())
        )
        await analysis_session.commit()

    return stats
