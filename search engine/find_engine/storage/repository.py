"""Репозиторий: upsert items/raw_records с дедупом по (source, external_id) + CRUD jobs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from find_engine.core.models import Item, Job, JobState, JobStats
from find_engine.storage.orm import ItemORM, JobORM, RawRecordORM


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Repository:
    """Тонкая обёртка над сессией. Транзакциями управляет вызывающий (orchestrator)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- items / raw_records --------------------------------------------

    async def upsert_item(self, item: Item, payload: dict | None = None) -> tuple[UUID, bool]:
        """Upsert по (source, external_id). Возвращает (item_id, inserted?).

        Если передан payload — пишем и сырую запись в raw_records.
        """
        fetched = item.fetched_at or _now()
        values = {
            "source": item.source,
            "external_id": item.external_id,
            "title": item.title,
            "url": item.url,
            "author": item.author,
            "body": item.body,
            "score": item.score,
            "tags": item.tags,
            "created_at": item.created_at,
            "fetched_at": fetched,
        }
        stmt = (
            pg_insert(ItemORM)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["source", "external_id"],
                set_={
                    "title": values["title"],
                    "url": values["url"],
                    "author": values["author"],
                    "body": values["body"],
                    "score": values["score"],
                    "tags": values["tags"],
                    "created_at": values["created_at"],
                    "fetched_at": values["fetched_at"],
                },
            )
            .returning(ItemORM.id, (literal_column("xmax") == 0).label("inserted"))
        )
        row = (await self.session.execute(stmt)).one()
        item_id, inserted = row.id, bool(row.inserted)

        if payload is not None:
            await self.session.execute(
                pg_insert(RawRecordORM).values(
                    item_id=item_id,
                    source=item.source,
                    external_id=item.external_id,
                    payload=payload,
                    fetched_at=fetched,
                )
            )
        return item_id, inserted

    async def get_item(self, source: str, external_id: str) -> ItemORM | None:
        stmt = select(ItemORM).where(
            ItemORM.source == source, ItemORM.external_id == external_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # ---- jobs -----------------------------------------------------------

    async def create_job(self, source: str, since: datetime | None) -> Job:
        orm = JobORM(source=source, status=JobState.queued.value, since=since, stats={})
        self.session.add(orm)
        await self.session.flush()
        return _job_from_orm(orm)

    async def update_job(
        self,
        job_id: UUID,
        *,
        status: JobState | None = None,
        cursor: str | None = None,
        stats: JobStats | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        orm = await self.session.get(JobORM, job_id)
        if orm is None:
            raise KeyError(f"Job not found: {job_id}")
        if status is not None:
            orm.status = status.value
        if cursor is not None:
            orm.cursor = cursor
        if stats is not None:
            orm.stats = stats.model_dump()
        if error is not None:
            orm.error = error
        if started_at is not None:
            orm.started_at = started_at
        if finished_at is not None:
            orm.finished_at = finished_at

    async def get_job(self, job_id: UUID) -> Job | None:
        orm = await self.session.get(JobORM, job_id)
        return _job_from_orm(orm) if orm else None

    async def last_successful_watermark(self, source: str) -> datetime | None:
        """`since` для следующего инкрементального запуска = finished_at последнего success."""
        stmt = (
            select(JobORM.finished_at)
            .where(JobORM.source == source, JobORM.status == JobState.success.value)
            .order_by(JobORM.finished_at.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()


def _job_from_orm(orm: JobORM) -> Job:
    return Job(
        id=orm.id,
        source=orm.source,
        status=JobState(orm.status),
        since=orm.since,
        cursor=orm.cursor,
        stats=JobStats(**(orm.stats or {})),
        error=orm.error,
        started_at=orm.started_at,
        finished_at=orm.finished_at,
    )
