"""Unit-тесты нормализации RedditSource. Сеть не нужна."""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

import pytest

from find_engine.config import Settings
from find_engine.core.models import RawRecord
from find_engine.sources.reddit import RedditSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_children() -> list[dict]:
    data = json.loads((FIXTURES / "reddit_new.json").read_text(encoding="utf-8"))
    return data["data"]["children"]


@pytest.fixture()
def source() -> RedditSource:
    return RedditSource(Settings())


@pytest.fixture()
def post_with_url() -> dict:
    return _load_children()[0]["data"]


@pytest.fixture()
def post_no_url() -> dict:
    return _load_children()[1]["data"]


def _make_raw(post: dict) -> RawRecord:
    return RawRecord(source="reddit", external_id=post["id"], payload=post)


class TestNormalizeWithUrl:
    def test_source(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.source == "reddit"

    def test_external_id(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.external_id == "abc123"

    def test_title(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.title == "GPT-5 rumours and what we actually know"

    def test_url_from_payload(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.url == "https://example.com/gpt5-rumours"

    def test_author(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.author == "ml_enthusiast"

    def test_score(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.score == 1042

    def test_subreddit_in_tags(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert "MachineLearning" in item.tags

    def test_flair_in_tags(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert "Discussion" in item.tags

    def test_created_at_utc(self, source: RedditSource, post_with_url: dict) -> None:
        item = source.normalize(_make_raw(post_with_url))
        assert item.created_at is not None
        assert item.created_at.tzinfo == timezone.utc
        assert item.created_at.timestamp() == post_with_url["created_utc"]


class TestNormalizePermalinkFallback:
    def test_url_falls_back_to_permalink(
        self, source: RedditSource, post_no_url: dict
    ) -> None:
        item = source.normalize(_make_raw(post_no_url))
        expected = "https://www.reddit.com/r/LocalLLaMA/comments/def456/running_llama3_locally/"
        assert item.url == expected

    def test_no_flair_tag(self, source: RedditSource, post_no_url: dict) -> None:
        item = source.normalize(_make_raw(post_no_url))
        assert item.tags == ["LocalLLaMA"]

    def test_created_at_tz_aware(self, source: RedditSource, post_no_url: dict) -> None:
        item = source.normalize(_make_raw(post_no_url))
        assert item.created_at is not None
        assert item.created_at.tzinfo is not None
