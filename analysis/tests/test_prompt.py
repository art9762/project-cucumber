"""Юнит-тесты для analysis/classify/prompt.py.

Чистые функции без I/O, без сети, без БД.
Покрывает: build_classify_prompt и parse_classification.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from analysis.classify.models import CategoryNode, ClassificationResult
from analysis.classify.prompt import _to_kebab, build_classify_prompt, parse_classification


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _make_item(
    *,
    title: str = "Test title",
    url: str = "https://example.com",
    body: str | None = "Some body text",
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


def _make_category(slug: str, title: str, approved: bool = True) -> CategoryNode:
    return CategoryNode(
        id=uuid.uuid4(),
        slug=slug,
        title=title,
        parent_id=None,
        approved=approved,
    )


def _json_str(**kwargs) -> str:
    return json.dumps(kwargs)


# ---------------------------------------------------------------------------
# Тесты _to_kebab (вспомогательный хелпер)
# ---------------------------------------------------------------------------

class TestToKebab:
    def test_lowercase(self) -> None:
        assert _to_kebab("AI") == "ai"

    def test_spaces_to_dashes(self) -> None:
        assert _to_kebab("machine learning") == "machine-learning"

    def test_underscores_to_dashes(self) -> None:
        assert _to_kebab("llm_agents") == "llm-agents"

    def test_mixed_case_and_spaces(self) -> None:
        assert _to_kebab("LLM Agents") == "llm-agents"

    def test_strips_non_ascii(self) -> None:
        assert _to_kebab("café & tea") == "caf-tea"

    def test_collapses_multiple_dashes(self) -> None:
        assert _to_kebab("a--b") == "a-b"

    def test_strips_leading_trailing_dashes(self) -> None:
        assert _to_kebab("-hello-") == "hello"

    def test_already_kebab(self) -> None:
        assert _to_kebab("llm-agents") == "llm-agents"


# ---------------------------------------------------------------------------
# Тесты build_classify_prompt
# ---------------------------------------------------------------------------

class TestBuildClassifyPrompt:
    def _categories(self) -> list[CategoryNode]:
        return [
            _make_category("ai", "Artificial Intelligence"),
            _make_category("science", "Science"),
            _make_category("business", "Business"),
        ]

    def test_returns_two_tuple(self) -> None:
        item = _make_item()
        result = build_classify_prompt(item, self._categories())
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_system_prompt_is_string(self) -> None:
        item = _make_item()
        system, _ = build_classify_prompt(item, self._categories())
        assert isinstance(system, str)

    def test_system_prompt_contains_all_category_slugs(self) -> None:
        item = _make_item()
        cats = self._categories()
        system, _ = build_classify_prompt(item, cats)
        for cat in cats:
            assert cat.slug in system

    def test_system_prompt_contains_all_category_titles(self) -> None:
        item = _make_item()
        cats = self._categories()
        system, _ = build_classify_prompt(item, cats)
        for cat in cats:
            assert cat.title in system

    def test_messages_is_nonempty_list(self) -> None:
        item = _make_item()
        _, messages = build_classify_prompt(item, self._categories())
        assert isinstance(messages, list)
        assert len(messages) > 0

    def test_messages_have_role_and_content(self) -> None:
        item = _make_item()
        _, messages = build_classify_prompt(item, self._categories())
        for msg in messages:
            assert "role" in msg
            assert "content" in msg

    def test_user_message_contains_title(self) -> None:
        item = _make_item(title="My special title")
        _, messages = build_classify_prompt(item, self._categories())
        combined = " ".join(m["content"] for m in messages)
        assert "My special title" in combined

    def test_user_message_contains_url(self) -> None:
        item = _make_item(url="https://news.ycombinator.com/item?id=42")
        _, messages = build_classify_prompt(item, self._categories())
        combined = " ".join(m["content"] for m in messages)
        assert "https://news.ycombinator.com/item?id=42" in combined

    def test_user_message_contains_source(self) -> None:
        item = _make_item(source="arxiv")
        _, messages = build_classify_prompt(item, self._categories())
        combined = " ".join(m["content"] for m in messages)
        assert "arxiv" in combined

    def test_long_body_is_truncated(self) -> None:
        long_body = "x" * 5000
        item = _make_item(body=long_body)
        _, messages = build_classify_prompt(item, self._categories())
        combined = " ".join(m["content"] for m in messages)
        # The original 5000-char body should NOT appear verbatim; truncated version will be shorter
        assert "x" * 5000 not in combined
        # But some body content IS present
        assert "x" * 100 in combined

    def test_empty_categories_list(self) -> None:
        item = _make_item()
        system, messages = build_classify_prompt(item, [])
        assert isinstance(system, str)
        assert isinstance(messages, list)

    def test_none_body_does_not_error(self) -> None:
        item = _make_item(body=None)
        system, messages = build_classify_prompt(item, self._categories())
        assert messages[0]["role"] == "user"


# ---------------------------------------------------------------------------
# Тесты parse_classification
# ---------------------------------------------------------------------------

class TestParseClassificationCleanJson:
    def test_basic_clean_json(self) -> None:
        text = _json_str(category="ai", confidence=0.9, suggested_subcategory=None)
        result = parse_classification(text)
        assert isinstance(result, ClassificationResult)
        assert result.category_slug == "ai"
        assert result.confidence == pytest.approx(0.9)
        assert result.suggested_subcategory_slug is None
        assert result.suggested_subcategory_title is None

    def test_with_full_subcategory(self) -> None:
        text = _json_str(
            category="ai",
            confidence=0.8,
            suggested_subcategory={"slug": "llm-agents", "title": "LLM Agents"},
        )
        result = parse_classification(text)
        assert result.suggested_subcategory_slug == "llm-agents"
        assert result.suggested_subcategory_title == "LLM Agents"
        assert result.has_suggestion is True

    def test_has_suggestion_false_when_no_subcategory(self) -> None:
        text = _json_str(category="science", confidence=0.7, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.has_suggestion is False


class TestParseClassificationFencedJson:
    def test_json_in_backtick_fence(self) -> None:
        payload = {"category": "business", "confidence": 0.6, "suggested_subcategory": None}
        text = f"```json\n{json.dumps(payload)}\n```"
        result = parse_classification(text)
        assert result.category_slug == "business"

    def test_json_in_plain_fence(self) -> None:
        payload = {"category": "science", "confidence": 0.5, "suggested_subcategory": None}
        text = f"```\n{json.dumps(payload)}\n```"
        result = parse_classification(text)
        assert result.category_slug == "science"


class TestParseClassificationProseWrapped:
    def test_json_with_leading_prose(self) -> None:
        payload = {"category": "ai", "confidence": 0.85, "suggested_subcategory": None}
        text = f"Sure, here is the result: {json.dumps(payload)} Hope that helps."
        result = parse_classification(text)
        assert result.category_slug == "ai"
        assert result.confidence == pytest.approx(0.85)

    def test_json_with_multiline_prose(self) -> None:
        payload = {"category": "business", "confidence": 0.4, "suggested_subcategory": None}
        text = f"Analysis complete.\n\n{json.dumps(payload)}\n\nEnd of response."
        result = parse_classification(text)
        assert result.category_slug == "business"


class TestParseClassificationMissingCategory:
    def test_missing_category_raises_value_error(self) -> None:
        text = _json_str(confidence=0.9, suggested_subcategory=None)
        with pytest.raises(ValueError, match="category"):
            parse_classification(text)

    def test_empty_string_category_raises_value_error(self) -> None:
        text = _json_str(category="", confidence=0.9, suggested_subcategory=None)
        with pytest.raises(ValueError):
            parse_classification(text)

    def test_whitespace_only_category_raises_value_error(self) -> None:
        text = _json_str(category="   ", confidence=0.9, suggested_subcategory=None)
        with pytest.raises(ValueError):
            parse_classification(text)


class TestParseClassificationConfidenceClamping:
    def test_confidence_above_1_clamped_to_1(self) -> None:
        text = _json_str(category="ai", confidence=1.5, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_below_0_clamped_to_0(self) -> None:
        text = _json_str(category="ai", confidence=-0.3, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_missing_defaults_to_0_5(self) -> None:
        text = json.dumps({"category": "ai", "suggested_subcategory": None})
        result = parse_classification(text)
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_string_unparseable_defaults_to_0_5(self) -> None:
        text = _json_str(category="ai", confidence="very high", suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_null_defaults_to_0_5(self) -> None:
        text = _json_str(category="ai", confidence=None, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_exactly_0(self) -> None:
        text = _json_str(category="ai", confidence=0.0, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_exactly_1(self) -> None:
        text = _json_str(category="ai", confidence=1.0, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.confidence == pytest.approx(1.0)


class TestParseClassificationPartialSubcategory:
    def test_slug_only_both_set_to_none(self) -> None:
        text = json.dumps({
            "category": "ai",
            "confidence": 0.8,
            "suggested_subcategory": {"slug": "transformers"},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug is None
        assert result.suggested_subcategory_title is None

    def test_title_only_both_set_to_none(self) -> None:
        text = json.dumps({
            "category": "ai",
            "confidence": 0.8,
            "suggested_subcategory": {"title": "Transformers"},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug is None
        assert result.suggested_subcategory_title is None

    def test_empty_slug_both_set_to_none(self) -> None:
        text = json.dumps({
            "category": "ai",
            "confidence": 0.8,
            "suggested_subcategory": {"slug": "", "title": "Transformers"},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug is None
        assert result.suggested_subcategory_title is None

    def test_empty_title_both_set_to_none(self) -> None:
        text = json.dumps({
            "category": "ai",
            "confidence": 0.8,
            "suggested_subcategory": {"slug": "transformers", "title": ""},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug is None
        assert result.suggested_subcategory_title is None


class TestParseClassificationSubcategoryNormalization:
    def test_subcategory_slug_normalized_to_kebab(self) -> None:
        text = json.dumps({
            "category": "ai",
            "confidence": 0.9,
            "suggested_subcategory": {"slug": "LLM Agents", "title": "LLM Agents"},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug == "llm-agents"

    def test_subcategory_slug_with_underscores_normalized(self) -> None:
        text = json.dumps({
            "category": "science",
            "confidence": 0.7,
            "suggested_subcategory": {"slug": "quantum_computing", "title": "Quantum Computing"},
        })
        result = parse_classification(text)
        assert result.suggested_subcategory_slug == "quantum-computing"

    def test_category_slug_normalized_to_kebab(self) -> None:
        text = _json_str(category="AI Research", confidence=0.9, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.category_slug == "ai-research"

    def test_category_slug_uppercase_normalized(self) -> None:
        text = _json_str(category="BUSINESS", confidence=0.6, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.category_slug == "business"

    def test_category_slug_with_spaces_normalized(self) -> None:
        text = _json_str(category="machine learning", confidence=0.8, suggested_subcategory=None)
        result = parse_classification(text)
        assert result.category_slug == "machine-learning"
