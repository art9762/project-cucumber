"""Оркестратор классификации (Фаза 1).

Запускает батчевую классификацию новых items дешёвой моделью через Trinity,
записывает результаты в item_analysis и фиксирует прогон в analysis_runs.

Изоляция ошибок: каждый item обрабатывается внутри SAVEPOINT (begin_nested).
На исключении SAVEPOINT откатывается — уже успешно обработанные items
остаются в транзакции и комитятся в конце.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysis.classify.categories import ensure_subcategory, get_by_slug, load_approved_top_level
from analysis.classify.models import ClassifyStats
from analysis.classify.prompt import build_classify_prompt, parse_classification
from analysis.config import get_settings
from analysis.storage.orm import AnalysisRunORM, ItemAnalysisORM
from analysis.storage.selector import select_new_items
from analysis.trinity import TrinityClient


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _process_item(
    *,
    item,
    analysis_session: AsyncSession,
    trinity: TrinityClient,
    approved_top_level,
    model: str | None,
    stats: ClassifyStats,
) -> None:
    """Классифицировать один item внутри вложенной транзакции (SAVEPOINT).

    При любом исключении SAVEPOINT откатывается, stats.failed инкрементируется.
    """
    stats.seen += 1
    try:
        async with analysis_session.begin_nested():
            system, messages = build_classify_prompt(item, approved_top_level)
            text = await trinity.complete(messages, model=model, system=system)
            res = parse_classification(text)

            node = await get_by_slug(analysis_session, res.category_slug)
            if node is None:
                node = await get_by_slug(analysis_session, "other")
            if node is None:
                raise ValueError(f"Категория '{res.category_slug}' и fallback 'other' не найдены")

            if res.has_suggestion:
                await ensure_subcategory(
                    analysis_session,
                    parent_slug=node.slug,
                    slug=res.suggested_subcategory_slug,  # type: ignore[arg-type]
                    title=res.suggested_subcategory_title,  # type: ignore[arg-type]
                )
                stats.suggested += 1

            model_used = model or get_settings().analysis_model_cheap
            analysis_session.add(
                ItemAnalysisORM(item_id=item.id, category_id=node.id, model_used=model_used)
            )
        stats.classified += 1
    except Exception as exc:  # noqa: BLE001
        stats.failed += 1
        stats.errors.append(f"{item.id}: {exc}")


async def run_classification(
    *,
    read_sessionmaker: async_sessionmaker[AsyncSession],
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    limit: int | None = None,
    model: str | None = None,
) -> ClassifyStats:
    """Полный прогон классификации одного батча новых items.

    1. Фиксирует analysis_runs-строку (kind='classify', status='running').
    2. Читает новые items через read_sessionmaker.
    3. Для каждого item: классифицирует, пишет item_analysis, обновляет stats.
    4. Обновляет analysis_runs-строку (status='success'/'failed', stats, finished_at).

    Возвращает ClassifyStats.
    """
    stats = ClassifyStats()
    run_id = None

    async with analysis_sessionmaker() as analysis_session:
        # Шаг 1: зафиксировать запуск (сразу commit — видно даже при падении процесса).
        run = AnalysisRunORM(kind="classify", status="running", started_at=_utcnow())
        analysis_session.add(run)
        await analysis_session.flush()
        run_id = run.id
        await analysis_session.commit()

        try:
            # Шаг 2: прочитать новые items через read-сессию.
            async with read_sessionmaker() as read_session:
                items = await select_new_items(read_session, limit=limit)

            # Шаг 3: загрузить утверждённые категории верхнего уровня (один раз).
            approved_top_level = await load_approved_top_level(analysis_session)

            # Шаг 4: обработать каждый item с изоляцией через SAVEPOINT.
            for item in items:
                await _process_item(
                    item=item,
                    analysis_session=analysis_session,
                    trinity=trinity,
                    approved_top_level=approved_top_level,
                    model=model,
                    stats=stats,
                )

            final_status = "success"
        except Exception as exc:  # noqa: BLE001
            final_status = "failed"
            stats.errors.append(f"fatal: {exc}")

        # Шаг 5: зафиксировать итог прогона.
        await analysis_session.execute(
            __import__("sqlalchemy").update(AnalysisRunORM)
            .where(AnalysisRunORM.id == run_id)
            .values(status=final_status, finished_at=_utcnow(), stats=stats.as_dict())
        )
        await analysis_session.commit()

    return stats
