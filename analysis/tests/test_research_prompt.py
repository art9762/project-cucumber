"""Юнит-тесты для analysis/research/prompt.py.

Чистые функции без I/O, без сети, без БД.
Покрывает: build_research_prompt и parse_research.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from analysis.research.models import Competitor, ResearchResult
from analysis.research.prompt import build_research_prompt, parse_research


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_item(
    *,
    title: str = "Test idea title",
    url: str = "https://example.com",
    body: str | None = "Some body text describing the idea.",
    source: str = "hackernews",
    author: str | None = None,
    score: int | None = None,
    tags: list[str] | None = None,
) -> Any:
    """Создать лёгкий stub ItemReadORM через SimpleNamespace (без ORM-инструментации)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        external_id="ext-1",
        title=title,
        url=url,
        body=body,
        source=source,
        author=author,
        score=score,
        tags=tags or [],
        created_at=datetime.now(timezone.utc),
        fetched_at=None,
    )


def _full_json(**overrides: Any) -> str:
    """Сгенерировать валидный JSON с дефолтными значениями всех полей."""
    defaults: dict[str, Any] = {
        "summary": "Это инновационная платформа для анализа данных с большим потенциалом.",
        "competitors": [
            {"name": "Acme Corp", "url": "https://acme.io", "note": "ближайший аналог"},
            {"name": "Beta Inc", "url": "https://beta.com", "note": "похожий продукт"},
        ],
        "maturity_signal": 0.6,
        "potential_signal": 0.7,
        "confidence": 0.8,
    }
    defaults.update(overrides)
    return json.dumps(defaults, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Тесты build_research_prompt
# ---------------------------------------------------------------------------

class TestBuildResearchPrompt:
    def test_returns_two_tuple(self) -> None:
        item = _make_item()
        result = build_research_prompt(item)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_system_prompt_is_string(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert isinstance(system, str)

    def test_messages_is_list_with_one_user_message(self) -> None:
        item = _make_item()
        _, messages = build_research_prompt(item)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert isinstance(messages[0]["content"], str)

    def test_user_message_contains_title(self) -> None:
        item = _make_item(title="Unique research idea XYZ")
        _, messages = build_research_prompt(item)
        assert "Unique research idea XYZ" in messages[0]["content"]

    def test_user_message_contains_url(self) -> None:
        item = _make_item(url="https://arxiv.org/abs/9999.0001")
        _, messages = build_research_prompt(item)
        assert "https://arxiv.org/abs/9999.0001" in messages[0]["content"]

    def test_user_message_contains_source(self) -> None:
        item = _make_item(source="arxiv")
        _, messages = build_research_prompt(item)
        assert "arxiv" in messages[0]["content"]

    def test_user_message_contains_author_when_set(self) -> None:
        item = _make_item(author="Jane Doe")
        _, messages = build_research_prompt(item)
        assert "Jane Doe" in messages[0]["content"]

    def test_user_message_skips_author_when_none(self) -> None:
        item = _make_item(author=None)
        _, messages = build_research_prompt(item)
        assert "Автор:" not in messages[0]["content"]

    def test_long_body_is_truncated(self) -> None:
        long_body = "z" * 5000
        item = _make_item(body=long_body)
        _, messages = build_research_prompt(item)
        content = messages[0]["content"]
        assert "z" * 5000 not in content
        assert "z" * 100 in content

    def test_body_exactly_at_limit_not_truncated(self) -> None:
        exact_body = "a" * 2000
        item = _make_item(body=exact_body)
        _, messages = build_research_prompt(item)
        content = messages[0]["content"]
        assert "…" not in content

    def test_none_body_does_not_error(self) -> None:
        item = _make_item(body=None)
        system, messages = build_research_prompt(item)
        assert isinstance(system, str)
        assert messages[0]["role"] == "user"

    def test_category_title_appears_in_system_prompt_when_given(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item, category_title="Artificial Intelligence")
        assert "Artificial Intelligence" in system

    def test_no_category_title_omits_category_hint(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item, category_title=None)
        assert "категории:" not in system

    def test_system_prompt_mentions_json(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert "JSON" in system

    def test_system_prompt_mentions_summary(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert "summary" in system

    def test_system_prompt_mentions_competitors(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert "competitors" in system

    def test_system_prompt_mentions_maturity_signal(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert "maturity_signal" in system

    def test_system_prompt_mentions_potential_signal(self) -> None:
        item = _make_item()
        system, _ = build_research_prompt(item)
        assert "potential_signal" in system


# ---------------------------------------------------------------------------
# Тесты parse_research — чистый JSON
# ---------------------------------------------------------------------------

class TestParseResearchCleanJson:
    def test_parses_summary(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert isinstance(result, ResearchResult)
        assert "инновационная" in result.summary

    def test_parses_competitors(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert len(result.competitors) == 2
        assert all(isinstance(c, Competitor) for c in result.competitors)

    def test_competitor_name_url_note(self) -> None:
        result = parse_research(_full_json(), sources=[])
        acme = next(c for c in result.competitors if c.name == "Acme Corp")
        assert acme.url == "https://acme.io"
        assert acme.note == "ближайший аналог"

    def test_parses_maturity_signal(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert result.maturity_signal == pytest.approx(0.6)

    def test_parses_potential_signal(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert result.potential_signal == pytest.approx(0.7)

    def test_parses_confidence(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert result.confidence == pytest.approx(0.8)

    def test_sources_passed_through(self) -> None:
        sources = ["https://source1.com", "https://source2.org"]
        result = parse_research(_full_json(), sources=sources)
        assert "https://source1.com" in result.sources
        assert "https://source2.org" in result.sources

    def test_competitor_urls_added_to_sources(self) -> None:
        result = parse_research(_full_json(), sources=[])
        assert "https://acme.io" in result.sources
        assert "https://beta.com" in result.sources

    def test_competitor_urls_not_duplicated_in_sources(self) -> None:
        sources = ["https://acme.io"]
        result = parse_research(_full_json(), sources=sources)
        assert result.sources.count("https://acme.io") == 1


# ---------------------------------------------------------------------------
# Тесты parse_research — JSON в ```-блоке
# ---------------------------------------------------------------------------

class TestParseResearchFencedJson:
    def test_json_in_backtick_json_fence(self) -> None:
        payload = json.loads(_full_json())
        text = f"```json\n{json.dumps(payload)}\n```"
        result = parse_research(text, sources=[])
        assert result.maturity_signal == pytest.approx(0.6)

    def test_json_in_plain_fence(self) -> None:
        payload = json.loads(_full_json())
        text = f"```\n{json.dumps(payload)}\n```"
        result = parse_research(text, sources=[])
        assert result.potential_signal == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Тесты parse_research — JSON с прозой вокруг
# ---------------------------------------------------------------------------

class TestParseResearchProseWrapped:
    def test_json_with_leading_prose(self) -> None:
        payload = json.loads(_full_json())
        text = f"Вот результат анализа: {json.dumps(payload)} Надеюсь, поможет."
        result = parse_research(text, sources=[])
        assert result.confidence == pytest.approx(0.8)

    def test_json_with_multiline_prose(self) -> None:
        payload = json.loads(_full_json())
        text = f"Анализ завершён.\n\n{json.dumps(payload)}\n\nКонец."
        result = parse_research(text, sources=[])
        assert "инновационная" in result.summary


# ---------------------------------------------------------------------------
# Тесты parse_research — пустой или отсутствующий summary → ValueError
# ---------------------------------------------------------------------------

class TestParseResearchSummaryRequired:
    def test_missing_summary_raises_value_error(self) -> None:
        data = {"competitors": [], "maturity_signal": 0.5,
                "potential_signal": 0.5, "confidence": 0.5}
        with pytest.raises(ValueError, match="summary"):
            parse_research(json.dumps(data), sources=[])

    def test_empty_summary_raises_value_error(self) -> None:
        data = {"summary": "", "competitors": [], "confidence": 0.5}
        with pytest.raises(ValueError, match="summary"):
            parse_research(json.dumps(data), sources=[])

    def test_whitespace_only_summary_raises_value_error(self) -> None:
        data = {"summary": "   ", "competitors": [], "confidence": 0.5}
        with pytest.raises(ValueError, match="summary"):
            parse_research(json.dumps(data), sources=[])

    def test_null_summary_raises_value_error(self) -> None:
        data = {"summary": None, "competitors": [], "confidence": 0.5}
        with pytest.raises(ValueError, match="summary"):
            parse_research(json.dumps(data), sources=[])


# ---------------------------------------------------------------------------
# Тесты parse_research — конкурент без name отбрасывается
# ---------------------------------------------------------------------------

class TestParseResearchCompetitorFiltering:
    def test_competitor_without_name_dropped(self) -> None:
        data = {
            "summary": "Valid summary here.",
            "competitors": [
                {"url": "https://no-name.com", "note": "no name entry"},
                {"name": "Valid Co", "url": "https://valid.com"},
            ],
            "confidence": 0.5,
        }
        result = parse_research(json.dumps(data), sources=[])
        assert len(result.competitors) == 1
        assert result.competitors[0].name == "Valid Co"

    def test_competitor_with_empty_name_dropped(self) -> None:
        data = {
            "summary": "Valid summary.",
            "competitors": [{"name": "", "url": "https://x.com"}],
            "confidence": 0.5,
        }
        result = parse_research(json.dumps(data), sources=[])
        assert len(result.competitors) == 0

    def test_all_valid_competitors_kept(self) -> None:
        data = {
            "summary": "Valid summary.",
            "competitors": [
                {"name": "Alpha", "url": "https://alpha.io"},
                {"name": "Beta"},
                {"name": "Gamma", "note": "some note"},
            ],
            "confidence": 0.5,
        }
        result = parse_research(json.dumps(data), sources=[])
        assert len(result.competitors) == 3

    def test_competitor_optional_url_none_when_missing(self) -> None:
        data = {
            "summary": "Valid summary.",
            "competitors": [{"name": "NoUrl Corp"}],
            "confidence": 0.5,
        }
        result = parse_research(json.dumps(data), sources=[])
        assert result.competitors[0].url is None

    def test_empty_competitors_list(self) -> None:
        data = {"summary": "Valid summary.", "competitors": [], "confidence": 0.5}
        result = parse_research(json.dumps(data), sources=[])
        assert result.competitors == []

    def test_missing_competitors_key(self) -> None:
        data = {"summary": "Valid summary.", "confidence": 0.5}
        result = parse_research(json.dumps(data), sources=[])
        assert result.competitors == []


# ---------------------------------------------------------------------------
# Тесты parse_research — клампинг сигналов
# ---------------------------------------------------------------------------

class TestParseResearchSignalClamping:
    def test_maturity_signal_above_1_clamped(self) -> None:
        result = parse_research(_full_json(maturity_signal=1.5), sources=[])
        assert result.maturity_signal == pytest.approx(1.0)

    def test_maturity_signal_below_0_clamped(self) -> None:
        result = parse_research(_full_json(maturity_signal=-0.3), sources=[])
        assert result.maturity_signal == pytest.approx(0.0)

    def test_potential_signal_above_1_clamped(self) -> None:
        result = parse_research(_full_json(potential_signal=2.0), sources=[])
        assert result.potential_signal == pytest.approx(1.0)

    def test_potential_signal_below_0_clamped(self) -> None:
        result = parse_research(_full_json(potential_signal=-1.0), sources=[])
        assert result.potential_signal == pytest.approx(0.0)

    def test_maturity_signal_null_returns_none(self) -> None:
        result = parse_research(_full_json(maturity_signal=None), sources=[])
        assert result.maturity_signal is None

    def test_potential_signal_null_returns_none(self) -> None:
        result = parse_research(_full_json(potential_signal=None), sources=[])
        assert result.potential_signal is None

    def test_maturity_signal_missing_returns_none(self) -> None:
        data = {"summary": "Valid.", "competitors": [], "confidence": 0.5}
        result = parse_research(json.dumps(data), sources=[])
        assert result.maturity_signal is None

    def test_confidence_above_1_clamped(self) -> None:
        result = parse_research(_full_json(confidence=1.5), sources=[])
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_below_0_clamped(self) -> None:
        result = parse_research(_full_json(confidence=-0.5), sources=[])
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_missing_defaults_to_0_5(self) -> None:
        data = {"summary": "Valid.", "competitors": []}
        result = parse_research(json.dumps(data), sources=[])
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_null_defaults_to_0_5(self) -> None:
        result = parse_research(_full_json(confidence=None), sources=[])
        assert result.confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Тесты parse_research — полный отказ парсинга
# ---------------------------------------------------------------------------

class TestParseResearchBrokenInput:
    def test_completely_broken_text_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_research("This is not JSON at all!!!", sources=[])

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_research("", sources=[])

    def test_truncated_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_research('{"summary": "partial', sources=[])


# ---------------------------------------------------------------------------
# Тесты parse_research — sources прокидываются
# ---------------------------------------------------------------------------

class TestParseResearchSources:
    def test_empty_sources_passed_through(self) -> None:
        data = {"summary": "Summary.", "competitors": []}
        result = parse_research(json.dumps(data), sources=[])
        assert result.sources == []

    def test_multiple_sources_preserved(self) -> None:
        sources = ["https://a.com", "https://b.org", "https://c.net"]
        data = {"summary": "Summary.", "competitors": []}
        result = parse_research(json.dumps(data), sources=sources)
        assert result.sources == sources

    def test_sources_order_preserved(self) -> None:
        sources = ["https://first.com", "https://second.com"]
        data = {"summary": "Summary.", "competitors": []}
        result = parse_research(json.dumps(data), sources=sources)
        assert result.sources[0] == "https://first.com"
        assert result.sources[1] == "https://second.com"
