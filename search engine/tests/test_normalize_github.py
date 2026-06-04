"""Unit-тест нормализации GitHub-источника. Сеть не используется."""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from find_engine.config import Settings
from find_engine.core.models import RawRecord
from find_engine.sources.github import GithubSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_repo(index: int = 0) -> dict:
    data = json.loads((FIXTURES / "github_search.json").read_text(encoding="utf-8"))
    return data["items"][index]


def _make_source() -> GithubSource:
    return GithubSource(Settings())


def test_normalize_title_and_url() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.title == repo["full_name"]
    assert item.url == repo["html_url"]


def test_normalize_author() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.author == repo["owner"]["login"]


def test_normalize_score() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.score == repo["stargazers_count"]


def test_normalize_tags_include_topics() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    for topic in repo["topics"]:
        assert topic in item.tags


def test_normalize_tags_include_language() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert repo["language"] in item.tags


def test_normalize_created_at_is_tz_aware() -> None:
    repo = _load_repo(0)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.created_at is not None
    assert item.created_at.tzinfo is not None
    assert item.created_at.tzinfo == timezone.utc


def test_normalize_source_field() -> None:
    repo = _load_repo(1)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.source == "github"
    assert item.external_id == str(repo["id"])


def test_normalize_body() -> None:
    repo = _load_repo(1)
    raw = RawRecord(source="github", external_id=str(repo["id"]), payload=repo)
    item = _make_source().normalize(raw)
    assert item.body == repo["description"]
