"""Tests: schedule router (GET/PUT), repository schedule methods, scheduler.start() with DB overrides."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from find_engine.core.scheduler import Scheduler
from find_engine.core.source import available_sources, clear_registry
from find_engine.sources import register_all
from find_engine.config import get_settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def registered_sources():
    """Ensure sources are registered (and clean up after)."""
    clear_registry()
    register_all(get_settings())
    yield
    clear_registry()


# ---------------------------------------------------------------------------
# Fake APScheduler (no real network/timer)
# ---------------------------------------------------------------------------


class FakeAPScheduler:
    def __init__(self):
        self._jobs: dict[str, object] = {}
        self.running = False

    def add_job(self, func, *, trigger, args, id, replace_existing, max_instances):
        self._jobs[id] = {"trigger": trigger, "args": args}

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)

    def remove_job(self, job_id: str):
        self._jobs.pop(job_id, None)

    def start(self):
        self.running = True

    def shutdown(self, wait=True):
        self.running = False


def _make_scheduler(crons: dict[str, str] | None = None) -> tuple[Scheduler, FakeAPScheduler]:
    from find_engine.config import Settings
    from find_engine.core.orchestrator import Orchestrator

    settings = Settings(
        cron_arxiv=crons.get("arxiv", "") if crons else "",
        cron_hackernews=crons.get("hackernews", "") if crons else "",
        cron_github=crons.get("github", "") if crons else "",
        cron_reddit=crons.get("reddit", "") if crons else "",
    )
    orchestrator = MagicMock(spec=Orchestrator)
    sched = Scheduler(orchestrator, settings)
    fake_ap = FakeAPScheduler()
    sched._scheduler = fake_ap
    return sched, fake_ap


# ---------------------------------------------------------------------------
# Scheduler unit tests
# ---------------------------------------------------------------------------


def test_start_applies_env_defaults():
    sched, fake_ap = _make_scheduler({"arxiv": "0 6 * * *"})
    sched.start()
    assert fake_ap.get_job("cron-arxiv") is not None
    assert sched.current_schedules() == {"arxiv": "0 6 * * *"}


def test_start_db_overrides_env():
    sched, fake_ap = _make_scheduler({"arxiv": "0 6 * * *"})
    sched.start(extra_schedules={"arxiv": "0 12 * * *", "github": "0 8 * * *"})
    assert sched.current_schedules()["arxiv"] == "0 12 * * *"
    assert sched.current_schedules()["github"] == "0 8 * * *"


def test_start_db_empty_cron_removes_env_job():
    sched, fake_ap = _make_scheduler({"arxiv": "0 6 * * *"})
    sched.start(extra_schedules={"arxiv": ""})
    # env added it, then DB cleared it
    assert "arxiv" not in sched.current_schedules()


def test_reschedule_valid_cron():
    sched, fake_ap = _make_scheduler()
    sched.start()
    sched.reschedule("arxiv", "0 9 * * *")
    assert sched.current_schedules()["arxiv"] == "0 9 * * *"
    assert fake_ap.get_job("cron-arxiv") is not None


def test_reschedule_empty_removes_job():
    sched, fake_ap = _make_scheduler({"arxiv": "0 6 * * *"})
    sched.start()
    sched.reschedule("arxiv", "")
    assert "arxiv" not in sched.current_schedules()


def test_reschedule_invalid_cron_raises():
    sched, _ = _make_scheduler()
    sched.start()
    with pytest.raises(Exception):  # ValueError from CronTrigger
        sched.reschedule("arxiv", "not-a-cron")


# ---------------------------------------------------------------------------
# Repository schedule methods (Postgres-only, skip if unavailable)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schedule_repository_roundtrip():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from find_engine.storage.orm import Base
    from find_engine.storage.repository import Repository

    engine = create_async_engine(get_settings().db_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres недоступен: {exc}")

    sm = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sm() as session:
            repo = Repository(session)
            await repo.upsert_schedule("arxiv", "0 6 * * *")
            await repo.upsert_schedule("github", "0 8 * * *")
            await session.commit()

        async with sm() as session:
            repo = Repository(session)
            schedules = await repo.get_schedules()
            assert schedules["arxiv"] == "0 6 * * *"
            assert schedules["github"] == "0 8 * * *"

        # upsert updates existing row
        async with sm() as session:
            repo = Repository(session)
            await repo.upsert_schedule("arxiv", "0 12 * * *")
            await session.commit()

        async with sm() as session:
            repo = Repository(session)
            schedules = await repo.get_schedules()
            assert schedules["arxiv"] == "0 12 * * *"

        # delete removes the row
        async with sm() as session:
            repo = Repository(session)
            await repo.delete_schedule("arxiv")
            await session.commit()

        async with sm() as session:
            repo = Repository(session)
            schedules = await repo.get_schedules()
            assert "arxiv" not in schedules
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


# ---------------------------------------------------------------------------
# API router tests (TestClient with mocked scheduler + sessionmaker)
# ---------------------------------------------------------------------------


def _make_test_app(scheduler: Scheduler) -> "FastAPI":
    from fastapi import FastAPI
    from find_engine.api.routers import schedule as schedule_router

    app = FastAPI()
    app.include_router(schedule_router.router)
    app.state.scheduler = scheduler
    return app


def _mock_sessionmaker():
    """Return a sessionmaker mock that yields a session supporting async context."""
    mock_sm = MagicMock()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.commit = AsyncMock()
    mock_session.get = AsyncMock(return_value=None)
    mock_sm.return_value = mock_session
    return mock_sm


@pytest.fixture
def scheduler_mock():
    sched, _ = _make_scheduler()
    sched.start()
    return sched


def test_get_schedule_returns_all_sources(scheduler_mock):
    app = _make_test_app(scheduler_mock)
    with TestClient(app) as client:
        resp = client.get("/schedule")
    assert resp.status_code == 200
    data = resp.json()
    assert "schedules" in data
    for src in available_sources():
        assert src in data["schedules"]
        assert data["schedules"][src] == ""


def test_put_schedule_valid_cron_persists_and_reschedules(scheduler_mock):
    app = _make_test_app(scheduler_mock)
    mock_sm = _mock_sessionmaker()
    mock_sm.return_value.execute = AsyncMock()

    with patch("find_engine.api.routers.schedule.get_sessionmaker", return_value=mock_sm):
        with TestClient(app) as client:
            resp = client.put("/schedule/arxiv", json={"cron": "0 6 * * *"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["schedules"]["arxiv"] == "0 6 * * *"
    assert scheduler_mock.current_schedules()["arxiv"] == "0 6 * * *"


def test_put_schedule_unknown_source_404(scheduler_mock):
    app = _make_test_app(scheduler_mock)
    with TestClient(app) as client:
        resp = client.put("/schedule/nonexistent", json={"cron": "0 6 * * *"})
    assert resp.status_code == 404


def test_put_schedule_invalid_cron_400(scheduler_mock):
    app = _make_test_app(scheduler_mock)
    with TestClient(app) as client:
        resp = client.put("/schedule/arxiv", json={"cron": "not-a-cron"})
    assert resp.status_code == 400


def test_put_schedule_empty_cron_clears(scheduler_mock):
    scheduler_mock.reschedule("arxiv", "0 6 * * *")
    assert "arxiv" in scheduler_mock.current_schedules()

    app = _make_test_app(scheduler_mock)
    mock_sm = _mock_sessionmaker()
    mock_sm.return_value.execute = AsyncMock()

    with patch("find_engine.api.routers.schedule.get_sessionmaker", return_value=mock_sm):
        with TestClient(app) as client:
            resp = client.put("/schedule/arxiv", json={"cron": ""})

    assert resp.status_code == 200
    assert resp.json()["schedules"]["arxiv"] == ""
    assert "arxiv" not in scheduler_mock.current_schedules()
