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
        self._crons: dict[str, str] = {}

    async def _run_source(self, source_name: str) -> None:
        source = get_source(source_name)
        job_id = await self._orchestrator.create_job(source)
        logger.info("Scheduler triggered %s → job %s", source_name, job_id)
        await self._orchestrator.run_job(job_id, source)

    def _apply_cron(self, name: str, cron: str) -> None:
        """Add/replace a single cron job. Stores in _crons."""
        self._scheduler.add_job(
            self._run_source,
            trigger=CronTrigger.from_crontab(cron, timezone="UTC"),
            args=[name],
            id=f"cron-{name}",
            replace_existing=True,
            max_instances=1,
        )
        self._crons[name] = cron

    def start(self, extra_schedules: dict[str, str] | None = None) -> None:
        """Start scheduler. extra_schedules (DB-persisted) override env defaults."""
        for name in available_sources():
            cron = self._settings.cron_for(name)
            if cron.strip():
                self._apply_cron(name, cron)
                logger.info("Scheduled %s (env): %s", name, cron)

        for name, cron in (extra_schedules or {}).items():
            if cron.strip():
                self._apply_cron(name, cron)
                logger.info("Scheduled %s (db): %s", name, cron)
            else:
                # DB explicitly cleared this source
                self._remove_job(name)

        self._scheduler.start()

    def _remove_job(self, source: str) -> None:
        job_id = f"cron-{source}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
        self._crons.pop(source, None)

    def reschedule(self, source: str, cron: str) -> None:
        """Set or clear a cron job for source. Raises ValueError on invalid cron."""
        if not cron.strip():
            self._remove_job(source)
            return
        # Let CronTrigger validate; raises ValueError on bad cron.
        trigger = CronTrigger.from_crontab(cron, timezone="UTC")
        self._scheduler.add_job(
            self._run_source,
            trigger=trigger,
            args=[source],
            id=f"cron-{source}",
            replace_existing=True,
            max_instances=1,
        )
        self._crons[source] = cron

    def current_schedules(self) -> dict[str, str]:
        """Return {source: cron_expr} for currently scheduled sources."""
        return dict(self._crons)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
