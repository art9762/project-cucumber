"""Оркестратор ресёрча (Фаза 3).

Запускает батчевый веб-ресёрч item'ов, у которых есть item_analysis,
но ещё нет item_research.  Каждый item обрабатывается через TrinityClient.search_complete;
результат — строка item_research (summary, competitors, sources, signals).

Изоляция ошибок: каждый item обрабатывается внутри SAVEPOINT (begin_nested).
На исключении SAVEPOINT откатывается — уже успешно разобранные item'ы
остаются в транзакции и комитятся в конце.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysis.config import get_settings
from analysis.research.models import ResearchStats
from analysis.research.prompt import build_research_prompt, parse_research
from analysis.research.selector import select_unresearched_items
from analysis.storage.orm import AnalysisRunORM, ItemReadORM, ItemResearchORM
from analysis.trinity import TrinityClient


def _utcnow() -> datetime:
    """Вернуть текущее UTC-время."""
    return datetime.now(timezone.utc)


async def _process_item(
    *,
    item: ItemReadORM,
    analysis_session: AsyncSession,
    trinity: TrinityClient,
    model: str,
    max_searches: int,
    stats: ResearchStats,
) -> None:
    """Разобрать один item внутри вложенной транзакции (SAVEPOINT).

    При любом исключении SAVEPOINT откатывается, stats.failed инкрементируется.
    """
    stats.seen += 1
    try:
        async with analysis_session.begin_nested():
            system, messages = build_research_prompt(item, category_title=None)
            text, sources = await trinity.search_complete(
                messages,
                model=model,
                system=system,
                max_searches=max_searches,
            )
            res = parse_research(text, sources)

            analysis_session.add(
                ItemResearchORM(
                    item_id=item.id,
                    summary=res.summary,
                    competitors=res.competitors_as_dicts(),
                    sources=res.sources,
                    maturity_signal=res.maturity_signal,
                    potential_signal=res.potential_signal,
                    model_used=model,
                )
            )
        stats.researched += 1
        stats.competitors_found += len(res.competitors)
    except Exception as exc:  # noqa: BLE001
        stats.failed += 1
        stats.errors.append(f"{item.id}: {exc}")


async def run_research(
    *,
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    limit: int | None = None,
    min_tier: str | None = None,
    min_coefficient: float | None = None,
    model: str | None = None,
    max_searches: int | None = None,
) -> ResearchStats:
    """Полный прогон веб-ресёрча одного батча неразобранных item'ов.

    1. Фиксирует analysis_runs-строку (kind='research', status='running').
    2. Читает item'ы без item_research через select_unresearched_items.
    3. Для каждого item: разбирает, вставляет item_research, ведёт stats.
    4. Обновляет analysis_runs-строку (status='success'/'failed', stats, finished_at).

    Args:
        analysis_sessionmaker: Async sessionmaker для записи в таблицы анализа.
        trinity: Клиент LLM-шлюза Trinity.
        limit: Максимальное число item'ов в батче; None — из Settings.
        min_tier: Минимальный тир (S/A/B/C/D); None — без фильтра.
        min_coefficient: Минимальный coefficient; None — без фильтра.
        model: Модель для ресёрча; None — из Settings.research_model.
        max_searches: Максимум поисков на item; None — из Settings.research_max_searches.

    Returns:
        :class:`ResearchStats` с агрегированной статистикой прогона.
    """
    settings = get_settings()
    model_eff = model or settings.research_model
    max_searches_eff = max_searches if max_searches is not None else settings.research_max_searches

    stats = ResearchStats()
    run_id = None

    async with analysis_sessionmaker() as analysis_session:
        # Шаг 1: зафиксировать запуск немедленно.
        run = AnalysisRunORM(kind="research", status="running", started_at=_utcnow())
        analysis_session.add(run)
        await analysis_session.flush()
        run_id = run.id
        await analysis_session.commit()

        try:
            # Шаг 2: прочитать item'ы без item_research.
            items = await select_unresearched_items(
                analysis_session,
                limit=limit,
                min_tier=min_tier,
                min_coefficient=min_coefficient,
            )

            # Шаг 3: обработать каждый item с изоляцией через SAVEPOINT.
            for item, _category_id in items:
                await _process_item(
                    item=item,
                    analysis_session=analysis_session,
                    trinity=trinity,
                    model=model_eff,
                    max_searches=max_searches_eff,
                    stats=stats,
                )

            final_status = "success"
        except Exception as exc:  # noqa: BLE001
            final_status = "failed"
            stats.errors.append(f"fatal: {exc}")

        # Шаг 4: зафиксировать итог прогона.
        await analysis_session.execute(
            update(AnalysisRunORM)
            .where(AnalysisRunORM.id == run_id)
            .values(status=final_status, finished_at=_utcnow(), stats=stats.as_dict())
        )
        await analysis_session.commit()

    return stats
