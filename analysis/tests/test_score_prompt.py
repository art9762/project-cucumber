"""Юнит-тесты для analysis/score/prompt.py.

Чистые функции без I/O, без сети, без БД.
Покрывает: build_score_prompt и parse_scores.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from analysis.score.models import PARAM_NAMES, ScoreParams, ScoreResult
from analysis.score.prompt import build_score_prompt, parse_scores


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


def _full_json(**overrides: Any) -> str:
    """Сгенерировать валидный JSON с дефолтными значениями всех 5 параметров."""
    defaults: dict[str, Any] = {
        "relevance": 0.9,
        "complexity": 0.4,
        "novelty": 0.7,
        "maturity": 0.3,
        "potential": 0.8,
        "confidence": 0.85,
        "rationale": "Краткое обоснование.",
    }
    defaults.update(overrides)
    return json.dumps(defaults)


# ---------------------------------------------------------------------------
# Тесты build_score_prompt
# ---------------------------------------------------------------------------

class TestBuildScorePrompt:
    def test_returns_two_tuple(self) -> None:
        item = _make_item()
        result = build_score_prompt(item)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_system_prompt_is_string(self) -> None:
        item = _make_item()
        system, _ = build_score_prompt(item)
        assert isinstance(system, str)

    def test_messages_is_list_with_one_user_message(self) -> None:
        item = _make_item()
        _, messages = build_score_prompt(item)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert isinstance(messages[0]["content"], str)

    def test_user_message_contains_title(self) -> None:
        item = _make_item(title="Unique item title XYZ")
        _, messages = build_score_prompt(item)
        assert "Unique item title XYZ" in messages[0]["content"]

    def test_user_message_contains_url(self) -> None:
        item = _make_item(url="https://arxiv.org/abs/1234.5678")
        _, messages = build_score_prompt(item)
        assert "https://arxiv.org/abs/1234.5678" in messages[0]["content"]

    def test_user_message_contains_source(self) -> None:
        item = _make_item(source="arxiv")
        _, messages = build_score_prompt(item)
        assert "arxiv" in messages[0]["content"]

    def test_user_message_contains_author_when_set(self) -> None:
        item = _make_item(author="John Doe")
        _, messages = build_score_prompt(item)
        assert "John Doe" in messages[0]["content"]

    def test_user_message_skips_author_when_none(self) -> None:
        item = _make_item(author=None)
        _, messages = build_score_prompt(item)
        assert "Автор:" not in messages[0]["content"]

    def test_long_body_is_truncated(self) -> None:
        long_body = "a" * 5000
        item = _make_item(body=long_body)
        _, messages = build_score_prompt(item)
        content = messages[0]["content"]
        assert "a" * 5000 not in content
        assert "a" * 100 in content

    def test_none_body_does_not_error(self) -> None:
        item = _make_item(body=None)
        system, messages = build_score_prompt(item)
        assert isinstance(system, str)
        assert messages[0]["role"] == "user"

    def test_category_title_appears_in_system_prompt_when_given(self) -> None:
        item = _make_item()
        system, _ = build_score_prompt(item, category_title="Artificial Intelligence")
        assert "Artificial Intelligence" in system

    def test_no_category_title_omits_category_hint(self) -> None:
        item = _make_item()
        system, _ = build_score_prompt(item, category_title=None)
        assert "категории:" not in system

    def test_system_prompt_mentions_all_param_names(self) -> None:
        item = _make_item()
        system, _ = build_score_prompt(item)
        for name in PARAM_NAMES:
            assert name in system

    def test_system_prompt_requires_json(self) -> None:
        item = _make_item()
        system, _ = build_score_prompt(item)
        assert "JSON" in system


# ---------------------------------------------------------------------------
# Тесты parse_scores — чистый JSON
# ---------------------------------------------------------------------------

class TestParseScoresCleanJson:
    def test_parses_all_five_params(self) -> None:
        text = _full_json()
        result = parse_scores(text)
        assert isinstance(result, ScoreResult)
        assert isinstance(result.params, ScoreParams)
        assert result.params.relevance == pytest.approx(0.9)
        assert result.params.complexity == pytest.approx(0.4)
        assert result.params.novelty == pytest.approx(0.7)
        assert result.params.maturity == pytest.approx(0.3)
        assert result.params.potential == pytest.approx(0.8)

    def test_parses_confidence(self) -> None:
        text = _full_json(confidence=0.85)
        result = parse_scores(text)
        assert result.confidence == pytest.approx(0.85)

    def test_parses_rationale(self) -> None:
        text = _full_json(rationale="Test rationale text.")
        result = parse_scores(text)
        assert result.rationale == "Test rationale text."

    def test_null_rationale_returns_none(self) -> None:
        text = _full_json(rationale=None)
        result = parse_scores(text)
        assert result.rationale is None

    def test_empty_rationale_returns_none(self) -> None:
        text = _full_json(rationale="")
        result = parse_scores(text)
        assert result.rationale is None


# ---------------------------------------------------------------------------
# Тесты parse_scores — JSON в ```-блоке
# ---------------------------------------------------------------------------

class TestParseScoresFencedJson:
    def test_json_in_backtick_json_fence(self) -> None:
        payload = json.loads(_full_json())
        text = f"```json\n{json.dumps(payload)}\n```"
        result = parse_scores(text)
        assert result.params.relevance == pytest.approx(0.9)

    def test_json_in_plain_fence(self) -> None:
        payload = json.loads(_full_json())
        text = f"```\n{json.dumps(payload)}\n```"
        result = parse_scores(text)
        assert result.params.novelty == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Тесты parse_scores — JSON с прозой вокруг
# ---------------------------------------------------------------------------

class TestParseScoresProseWrapped:
    def test_json_with_leading_prose(self) -> None:
        payload = json.loads(_full_json())
        text = f"Вот результат оценки: {json.dumps(payload)} Надеюсь, поможет."
        result = parse_scores(text)
        assert result.params.potential == pytest.approx(0.8)

    def test_json_with_multiline_prose(self) -> None:
        payload = json.loads(_full_json())
        text = f"Анализ завершён.\n\n{json.dumps(payload)}\n\nКонец."
        result = parse_scores(text)
        assert result.confidence == pytest.approx(0.85)


# ---------------------------------------------------------------------------
# Тесты parse_scores — пропущенные параметры
# ---------------------------------------------------------------------------

class TestParseScoresMissingParams:
    def test_missing_param_defaults_to_0_5(self) -> None:
        data = {
            "relevance": 0.9,
            # complexity отсутствует
            "novelty": 0.7,
            "maturity": 0.3,
            "potential": 0.8,
            "confidence": 0.85,
        }
        result = parse_scores(json.dumps(data))
        assert result.params.complexity == pytest.approx(0.5)

    def test_all_params_missing_defaults_to_0_5(self) -> None:
        result = parse_scores(json.dumps({"confidence": 0.6}))
        for name in PARAM_NAMES:
            assert getattr(result.params, name) == pytest.approx(0.5)

    def test_missing_confidence_defaults_to_0_5(self) -> None:
        data = {name: 0.5 for name in PARAM_NAMES}
        result = parse_scores(json.dumps(data))
        assert result.confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Тесты parse_scores — клампинг confidence
# ---------------------------------------------------------------------------

class TestParseScoresConfidenceClamping:
    def test_confidence_above_1_clamped_to_1(self) -> None:
        result = parse_scores(_full_json(confidence=1.5))
        assert result.confidence == pytest.approx(1.0)

    def test_confidence_below_0_clamped_to_0(self) -> None:
        result = parse_scores(_full_json(confidence=-0.3))
        assert result.confidence == pytest.approx(0.0)

    def test_confidence_null_defaults_to_0_5(self) -> None:
        result = parse_scores(_full_json(confidence=None))
        assert result.confidence == pytest.approx(0.5)

    def test_confidence_string_defaults_to_0_5(self) -> None:
        result = parse_scores(_full_json(confidence="very high"))
        assert result.confidence == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Тесты parse_scores — клампинг параметров
# ---------------------------------------------------------------------------

class TestParseScoresParamClamping:
    def test_param_above_1_clamped(self) -> None:
        result = parse_scores(_full_json(relevance=2.5))
        assert result.params.relevance == pytest.approx(1.0)

    def test_param_below_0_clamped(self) -> None:
        result = parse_scores(_full_json(novelty=-0.5))
        assert result.params.novelty == pytest.approx(0.0)

    def test_param_string_defaults_to_0_5(self) -> None:
        result = parse_scores(_full_json(maturity="high"))
        assert result.params.maturity == pytest.approx(0.5)

    def test_param_null_defaults_to_0_5(self) -> None:
        result = parse_scores(_full_json(potential=None))
        assert result.params.potential == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Тесты parse_scores — полный отказ парсинга
# ---------------------------------------------------------------------------

class TestParseScoresBrokenInput:
    def test_completely_broken_text_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_scores("This is not JSON at all!!!")

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_scores("")

    def test_truncated_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            parse_scores('{"relevance": 0.9, "complexity":')


# ---------------------------------------------------------------------------
# Тесты parse_scores — длинный rationale
# ---------------------------------------------------------------------------

class TestParseScoresRationale:
    def test_long_rationale_trimmed_to_500_chars(self) -> None:
        long_rationale = "x" * 1000
        result = parse_scores(_full_json(rationale=long_rationale))
        assert result.rationale is not None
        assert len(result.rationale) <= 500

    def test_short_rationale_preserved(self) -> None:
        short = "Краткое обоснование."
        result = parse_scores(_full_json(rationale=short))
        assert result.rationale == short
