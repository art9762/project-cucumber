"""Cron-планировщик: по расписанию ставит и запускает jobs для источников."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from find_engine.config import Settings
from find_engine.core.orchestrator import Orchestrator
from find_engine.core.source import available_sources, get_source

logger = logging.getLogger(__name__)


class Scheduler:
    """Тонкая обёртка над APScheduler. Для каждого источника с непустым cron —
    периодически создаёт job и сразу её выполняет."""

    def __init__(self, orchestrator: Orchestrator, settings: Settings) -> None:
        self._orchestrator = orchestrator
        self._settings = settings
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    async def _run_source(self, source_name: str) -> None:
        source = get_source(source_name)
        job_id = await self._orchestrator.create_job(source)
        logger.info("Scheduler triggered %s → job %s", source_name, job_id)
        await self._orchestrator.run_job(job_id, source)

    def start(self) -> None:
        for name in available_sources():
            cron = self._settings.cron_for(name)
            if not cron.strip():
                continue
            self._scheduler.add_job(
                self._run_source,
                trigger=CronTrigger.from_crontab(cron, timezone="UTC"),
                args=[name],
                id=f"cron-{name}",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Scheduled %s: %s", name, cron)
        self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
