"""Оркестратор скоринга (Фаза 2).

Запускает батчевый скоринг item'ов, у которых уже есть category_id (Фаза 1),
но ещё не выставлен coefficient.  Дешёвая модель обрабатывает каждый item;
при низкой уверенности или пограничном coefficient — эскалируем на глубокую.

Изоляция ошибок: каждый item обрабатывается внутри SAVEPOINT (begin_nested).
На исключении SAVEPOINT откатывается — уже успешно проскоренные item'ы
остаются в транзакции и комитятся в конце.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analysis.config import get_settings
from analysis.score.formula import (
    assign_tier,
    compute_coefficient,
    load_scoring_config,
    should_escalate,
)
from analysis.score.models import ScoreStats, ScoringConfig
from analysis.score.prompt import build_score_prompt, parse_scores
from analysis.score.selector import select_unscored_items
from analysis.storage.orm import AnalysisRunORM, ItemAnalysisORM, ItemReadORM
from analysis.trinity import TrinityClient


def _utcnow() -> datetime:
    """Вернуть текущее UTC-время."""
    return datetime.now(timezone.utc)


async def _process_item(
    *,
    item: ItemReadORM,
    category_id: object,
    analysis_session: AsyncSession,
    trinity: TrinityClient,
    cheap_model: str,
    deep_model: str | None,
    config: ScoringConfig,
    stats: ScoreStats,
) -> None:
    """Проскорить один item внутри вложенной транзакции (SAVEPOINT).

    При любом исключении SAVEPOINT откатывается, stats.failed инкрементируется.
    """
    stats.seen += 1
    try:
        async with analysis_session.begin_nested():
            system, messages = build_score_prompt(item, None)
            text = await trinity.complete(messages, model=cheap_model, system=system)
            res = parse_scores(text)
            coef = compute_coefficient(res.params, config)
            model_used = cheap_model

            if should_escalate(res, coef, config) and deep_model:
                text2 = await trinity.complete(messages, model=deep_model, system=system)
                res = parse_scores(text2)
                coef = compute_coefficient(res.params, config)
                model_used = deep_model
                stats.escalated += 1

            tier = assign_tier(coef, config)

            await analysis_session.execute(
                update(ItemAnalysisORM)
                .where(ItemAnalysisORM.item_id == item.id)
                .values(
                    scores=res.params.as_dict(),
                    coefficient=coef,
                    tier=tier,
                    model_used=model_used,
                )
            )
        stats.scored += 1
        stats.record_tier(tier)
    except Exception as exc:  # noqa: BLE001
        stats.failed += 1
        stats.errors.append(f"{item.id}: {exc}")


async def run_scoring(
    *,
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    config: ScoringConfig | None = None,
    limit: int | None = None,
    cheap_model: str | None = None,
    deep_model: str | None = None,
) -> ScoreStats:
    """Полный прогон скоринга одного батча классифицированных item'ов.

    1. Фиксирует analysis_runs-строку (kind='score', status='running').
    2. Читает item'ы с category_id != NULL и coefficient IS NULL.
    3. Для каждого item: скорит, обновляет item_analysis, ведёт stats.
    4. Обновляет analysis_runs-строку (status='success'/'failed', stats, finished_at).

    Args:
        analysis_sessionmaker: Async sessionmaker для записи в таблицы анализа.
        trinity: Клиент LLM-шлюза Trinity.
        config: Конфигурация формулы; если None — загружается из env.
        limit: Максимальное число item'ов в батче; None — из Settings.
        cheap_model: Дешёвая модель; None — из Settings.
        deep_model: Глубокая модель; None — из Settings.

    Returns:
        :class:`ScoreStats` с агрегированной статистикой прогона.
    """
    effective_config = config or load_scoring_config()
    settings = get_settings()
    cheap = cheap_model or settings.analysis_model_cheap
    deep = deep_model or settings.analysis_model_deep

    stats = ScoreStats()
    run_id = None

    async with analysis_sessionmaker() as analysis_session:
        # Шаг 1: зафиксировать запуск немедленно.
        run = AnalysisRunORM(kind="score", status="running", started_at=_utcnow())
        analysis_session.add(run)
        await analysis_session.flush()
        run_id = run.id
        await analysis_session.commit()

        try:
            # Шаг 2: прочитать item'ы, готовые к скорингу.
            items = await select_unscored_items(analysis_session, limit=limit)

            # Шаг 3: обработать каждый item с изоляцией через SAVEPOINT.
            for item, category_id in items:
                await _process_item(
                    item=item,
                    category_id=category_id,
                    analysis_session=analysis_session,
                    trinity=trinity,
                    cheap_model=cheap,
                    deep_model=deep,
                    config=effective_config,
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
