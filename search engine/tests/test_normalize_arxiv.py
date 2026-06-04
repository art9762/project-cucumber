"""Тесты нормализации ArxivSource — без обращения к сети.

Загружает фикстуру tests/fixtures/arxiv_query.xml, парсит её через feedparser
(ровно так же, как делает плагин) и проверяет, что normalize возвращает
корректный Item.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import feedparser
import pytest

from find_engine.config import Settings
from find_engine.core.models import RawRecord
from find_engine.sources.arxiv import ArxivSource

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_query.xml"


@pytest.fixture(scope="module")
def src() -> ArxivSource:
    return ArxivSource(Settings())


@pytest.fixture(scope="module")
def feed_entries():
    xml = FIXTURE.read_text(encoding="utf-8")
    return feedparser.parse(xml).entries


@pytest.fixture(scope="module")
def raw_records(src: ArxivSource, feed_entries):
    return [src._entry_to_raw(e) for e in feed_entries]


class TestEntryToRaw:
    def test_returns_raw_record(self, raw_records):
        assert all(isinstance(r, RawRecord) for r in raw_records)

    def test_source_field(self, raw_records):
        assert all(r.source == "arxiv" for r in raw_records)

    def test_external_id_strips_version(self, raw_records):
        assert raw_records[0].external_id == "2403.09000"
        assert raw_records[1].external_id == "2403.08765"

    def test_payload_is_plain_dict(self, raw_records):
        """Payload должен быть JSON-совместимым словарём без time.struct_time."""
        import json
        import time
        for r in raw_records:
            assert isinstance(r.payload, dict)
            # JSON roundtrip не должен падать
            json.dumps(r.payload)
            # Не должно быть time.struct_time в значениях
            for v in r.payload.values():
                assert not isinstance(v, time.struct_time)


class TestNormalize:
    def test_source(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.source == "arxiv"

    def test_external_id(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.external_id == "2403.09000"

    def test_title_whitespace_collapsed(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.title == "Attention Is All You Need: Revisited with Sparse Transformers"
        # Вторая запись — заголовок с переносом строки в XML
        item2 = src.normalize(raw_records[1])
        assert "\n" not in item2.title
        assert item2.title == "Large Language Models as Reasoning Agents: A Survey"

    def test_url(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.url == "http://arxiv.org/abs/2403.09000v1"

    def test_author_first_only(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.author == "Alice Smith"

    def test_author_single(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[1])
        assert item.author == "Carol Williams"

    def test_body_present(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.body is not None
        assert len(item.body) > 10

    def test_tags_list(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert isinstance(item.tags, list)
        assert "cs.LG" in item.tags
        assert "cs.AI" in item.tags

    def test_tags_second_entry(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[1])
        assert "cs.AI" in item.tags
        assert "cs.CL" in item.tags

    def test_score_is_none(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.score is None

    def test_created_at_is_datetime(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert isinstance(item.created_at, datetime)

    def test_created_at_timezone_aware(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.created_at is not None
        assert item.created_at.tzinfo is not None

    def test_created_at_utc(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        assert item.created_at is not None
        assert item.created_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]

    def test_created_at_value(self, src: ArxivSource, raw_records):
        item = src.normalize(raw_records[0])
        expected = datetime(2024, 3, 14, 17, 59, 31, tzinfo=timezone.utc)
        assert item.created_at == expected
