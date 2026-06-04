"""Прогон orchestrator с мок-источником и in-memory репозиторием (без Postgres)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from find_engine.core.models import Item, Job, JobState, RawRecord
from find_engine.core.orchestrator import Orchestrator


class MockSource:
    name = "mock"

    def __init__(self, raws: list[RawRecord]) -> None:
        self._raws = raws

    async def fetch(self, since, cursor) -> AsyncIterator[RawRecord]:
        for r in self._raws:
            yield r

    def normalize(self, raw: RawRecord) -> Item:
        return Item(
            source=raw.source,
            external_id=raw.external_id,
            title=raw.payload["title"],
            url=raw.payload["url"],
        )


class FakeRepo:
    """In-memory репозиторий: дедуп по (source, external_id) как в Postgres-upsert."""

    def __init__(self, session) -> None:  # noqa: ANN001 — session игнорируем
        # Общее состояние между инстансами — имитируем единую БД.
        self.store = _SHARED

    async def last_successful_watermark(self, source: str):
        return self.store["watermark"].get(source)

    async def create_job(self, source: str, since) -> Job:
        job = Job(source=source, since=since)
        self.store["jobs"][job.id] = job
        return job

    async def get_job(self, job_id: UUID):
        return self.store["jobs"].get(job_id)

    async def update_job(self, job_id, *, status=None, cursor=None, stats=None,
                         error=None, started_at=None, finished_at=None) -> None:
        job = self.store["jobs"][job_id]
        if status is not None:
            job.status = status
        if stats is not None:
            job.stats = stats
        if error is not None:
            job.error = error
        if started_at is not None:
            job.started_at = started_at
        if finished_at is not None:
            job.finished_at = finished_at

    async def upsert_item(self, item: Item, payload=None) -> tuple[UUID, bool]:
        key = (item.source, item.external_id)
        items = self.store["items"]
        inserted = key not in items
        if inserted:
            items[key] = uuid4()
        return items[key], inserted


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        pass

    async def rollback(self):
        pass


def fake_sessionmaker():
    return FakeSession()


_SHARED: dict = {}


@pytest.fixture(autouse=True)
def _reset_shared():
    _SHARED.clear()
    _SHARED.update({"jobs": {}, "items": {}, "watermark": {}})
    yield


@pytest.fixture
def orchestrator() -> Orchestrator:
    return Orchestrator(fake_sessionmaker, repository_factory=FakeRepo)


def _raw(i: int) -> RawRecord:
    return RawRecord(
        source="mock",
        external_id=str(i),
        payload={"title": f"t{i}", "url": f"http://x/{i}"},
    )


async def test_run_job_collects_and_dedups(orchestrator: Orchestrator):
    source = MockSource([_raw(1), _raw(2), _raw(2)])  # дубль external_id=2
    job_id = await orchestrator.create_job(source)

    stats = await orchestrator.run_job(job_id, source)

    assert stats.fetched == 3
    assert stats.inserted == 2  # уникальных
    assert stats.updated == 1   # повтор → update
    assert _SHARED["jobs"][job_id].status is JobState.success


async def test_second_run_is_incremental_no_new_inserts(orchestrator: Orchestrator):
    source = MockSource([_raw(1), _raw(2)])
    job1 = await orchestrator.create_job(source)
    await orchestrator.run_job(job1, source)

    # Повторный прогон тех же записей → всё updated, ничего нового.
    job2 = await orchestrator.create_job(source)
    stats = await orchestrator.run_job(job2, source)

    assert stats.inserted == 0
    assert stats.updated == 2


async def test_failed_job_records_error(orchestrator: Orchestrator):
    class Boom(MockSource):
        async def fetch(self, since, cursor):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    source = Boom([])
    job_id = await orchestrator.create_job(source)
    with pytest.raises(RuntimeError):
        await orchestrator.run_job(job_id, source)

    job = _SHARED["jobs"][job_id]
    assert job.status is JobState.failed
    assert job.error == "boom"
