"""Прогон job: watermark → Source.fetch → normalize → upsert → обновление статистики.

Точка, где встречаются плагин-источник и хранилище. Ядро не знает деталей источников.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from find_engine.core.models import JobState, JobStats
from find_engine.core.source import Source
from find_engine.storage.repository import Repository

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Orchestrator:
    """Запускает сбор для одного источника в рамках одной job.

    Каждая job выполняется в своей сессии/транзакции, чтобы статус и данные
    фиксировались атомарно по завершении.

    `repository_factory` инъектируется для тестов (мок-репозиторий без Postgres).
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        repository_factory: Callable[[AsyncSession], Repository] = Repository,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._repo = repository_factory

    async def create_job(self, source: Source) -> UUID:
        """Поставить job: вычислить watermark из последнего успешного запуска."""
        async with self._sessionmaker() as session:
            repo = self._repo(session)
            since = await repo.last_successful_watermark(source.name)
            job = await repo.create_job(source.name, since)
            await session.commit()
            return job.id

    async def run_job(self, job_id: UUID, source: Source) -> JobStats:
        """Выполнить ранее созданную job. Исключения ловим → статус failed."""
        async with self._sessionmaker() as session:
            repo = self._repo(session)
            job = await repo.get_job(job_id)
            if job is None:
                raise KeyError(f"Job not found: {job_id}")

            await repo.update_job(
                job_id, status=JobState.running, started_at=_now()
            )
            await session.commit()

            stats = JobStats()
            try:
                async for raw in source.fetch(job.since, None):
                    stats.fetched += 1
                    item = source.normalize(raw)
                    _, inserted = await repo.upsert_item(item, payload=raw.payload)
                    if inserted:
                        stats.inserted += 1
                    else:
                        stats.updated += 1
                await repo.update_job(
                    job_id,
                    status=JobState.success,
                    stats=stats,
                    finished_at=_now(),
                )
                await session.commit()
            except Exception as exc:  # noqa: BLE001 — фиксируем ошибку в job и пробрасываем
                await session.rollback()
                async with self._sessionmaker() as err_session:
                    err_repo = self._repo(err_session)
                    await err_repo.update_job(
                        job_id,
                        status=JobState.failed,
                        stats=stats,
                        error=str(exc),
                        finished_at=_now(),
                    )
                    await err_session.commit()
                logger.exception("Job %s (%s) failed", job_id, source.name)
                raise
            return stats
