"""Unit-тесты нормализации источника Hacker News. Сеть не используется."""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from find_engine.config import Settings
from find_engine.core.models import RawRecord
from find_engine.sources.hackernews import HackerNewsSource

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture() -> dict:
    return json.loads((FIXTURES / "hackernews_search.json").read_text(encoding="utf-8"))


def _make_source() -> HackerNewsSource:
    return HackerNewsSource(Settings())


class TestHackerNewsNormalize:
    def test_normalize_full_hit(self) -> None:
        data = _load_fixture()
        hit = data["hits"][0]
        raw = RawRecord(source="hackernews", external_id=str(hit["objectID"]), payload=hit)
        item = _make_source().normalize(raw)

        assert item.source == "hackernews"
        assert item.external_id == "39876543"
        assert item.title == "Show HN: Open-source LLM agent framework in Python"
        assert item.url == "https://github.com/example/llm-agent"
        assert item.author == "jsmith"
        assert item.score == 312
        assert item.body is None
        assert "story" in item.tags
        assert item.created_at is not None
        assert item.created_at.tzinfo is not None
        assert item.created_at.tzinfo == timezone.utc

    def test_normalize_url_fallback(self) -> None:
        """Хит без url должен получить ссылку на HN-страницу."""
        data = _load_fixture()
        hit = data["hits"][1]
        assert hit["url"] is None, "fixture hit[1] should have null url"

        raw = RawRecord(source="hackernews", external_id=str(hit["objectID"]), payload=hit)
        item = _make_source().normalize(raw)

        assert item.url == f"https://news.ycombinator.com/item?id={hit['objectID']}"
        assert item.body is not None
        assert item.score == 156

    def test_normalize_created_at_is_utc(self) -> None:
        data = _load_fixture()
        hit = data["hits"][0]
        raw = RawRecord(source="hackernews", external_id=str(hit["objectID"]), payload=hit)
        item = _make_source().normalize(raw)

        assert item.created_at is not None
        assert item.created_at.tzinfo == timezone.utc
        assert item.created_at.year == 2024

    def test_normalize_tags_are_strings(self) -> None:
        data = _load_fixture()
        hit = data["hits"][0]
        raw = RawRecord(source="hackernews", external_id=str(hit["objectID"]), payload=hit)
        item = _make_source().normalize(raw)

        assert all(isinstance(t, str) for t in item.tags)

    def test_normalize_source_constant(self) -> None:
        data = _load_fixture()
        for hit in data["hits"]:
            raw = RawRecord(
                source="hackernews", external_id=str(hit["objectID"]), payload=hit
            )
            item = _make_source().normalize(raw)
            assert item.source == "hackernews"
