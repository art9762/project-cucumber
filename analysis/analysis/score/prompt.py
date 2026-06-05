"""Построение промпта скоринга и парсинг ответа модели (Фаза 2).

Чистые функции без I/O: только строки, JSON, регулярные выражения.
Используется оркестратором скоринга для вызова TrinityClient.
"""

from __future__ import annotations

import json
import re
from typing import Any

from analysis.score.models import PARAM_NAMES, ScoreParams, ScoreResult
from analysis.storage.orm import ItemReadORM

# Максимальная длина тела item в промпте (символов) — чтобы промпт оставался дешёвым.
_BODY_MAX_CHARS = 2000

# Максимальная длина rationale (символов) — краткость для аудита.
_RATIONALE_MAX_CHARS = 500


def build_score_prompt(
    item: ItemReadORM,
    category_title: str | None = None,
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для TrinityClient.complete(messages, system=...).

    - Просит модель выставить оценку по 5 параметрам (PARAM_NAMES), каждый 0.0–1.0.
    - Дополнительно просит confidence 0..1 и краткое rationale.
    - Требует строгий JSON-ответ без лишнего текста.
    - Если передан category_title — упоминает его как контекст.
    - messages = [{"role":"user","content": <title/url/source/author/body>}].
    - Длинное тело item обрезается до ~2000 символов.
    """
    category_hint = (
        f" Материал относится к категории: «{category_title}»."
        if category_title
        else ""
    )

    system_prompt = (
        "Ты — эксперт по оценке технологических материалов (статьи, проекты, идеи)."
        f"{category_hint}"
        " Твоя задача — выставить оценку по пяти параметрам:\n\n"
        "  - relevance  (актуальность, 0.0–1.0): насколько тема горячая прямо сейчас.\n"
        "  - complexity (сложность реализации, 0.0–1.0): выше = труднее.\n"
        "  - novelty    (новизна, 0.0–1.0): насколько идея незаезженная.\n"
        "  - maturity   (зрелость/насыщённость рынка, 0.0–1.0): выше = больше готовых решений.\n"
        "  - potential  (рыночный потенциал / применимость, 0.0–1.0): выше = больше.\n\n"
        "Правила ответа:\n"
        "1. Отвечай ТОЛЬКО валидным JSON-объектом — без пояснений, без ```-блоков.\n"
        "2. Все пять параметров обязательны: числа от 0.0 до 1.0.\n"
        "3. Поле \"confidence\": уверенность в оценке, число от 0.0 до 1.0.\n"
        "4. Поле \"rationale\": строка до 500 символов с кратким обоснованием.\n"
        "Пример: {\"relevance\": 0.9, \"complexity\": 0.4, \"novelty\": 0.7,"
        " \"maturity\": 0.3, \"potential\": 0.8, \"confidence\": 0.85,"
        " \"rationale\": \"Горячая тема, низкая насыщённость рынка.\"}"
    )

    body = item.body or ""
    if len(body) > _BODY_MAX_CHARS:
        body = body[:_BODY_MAX_CHARS] + "…"

    parts: list[str] = [
        f"Заголовок: {item.title}",
        f"URL: {item.url}",
        f"Источник: {item.source}",
    ]
    if item.author:
        parts.append(f"Автор: {item.author}")
    if body:
        parts.append(f"Тело:\n{body}")

    user_content = "\n".join(parts)
    messages: list[dict] = [{"role": "user", "content": user_content}]
    return system_prompt, messages


def _extract_json_object(text: str) -> str:
    """Извлечь первый {...} из текста (включая вложенные скобки).

    Сначала пробуем ```json-блок, затем ищем outermost {}.
    """
    # Попытка 1: ```json ... ``` блок
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Попытка 2: найти outermost {...} в тексте
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _coerce_unit(raw: Any, default: float = 0.5) -> float:
    """Привести значение к float в диапазоне [0.0, 1.0]; при ошибке вернуть default."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, value))


def parse_scores(text: str) -> ScoreResult:
    """Разобрать ответ модели (JSON, возможно в ```-блоке или с мусором по краям).

    - Принимает чистый JSON, JSON в ```json-блоке, JSON с прозой вокруг него.
    - Каждый из 5 параметров: float, клампится в [0.0, 1.0]; при отсутствии/ошибке — 0.5.
    - confidence: float, клампится в [0.0, 1.0]; при отсутствии/ошибке — 0.5.
    - rationale: str | None, обрезается до ~500 символов.
    - Если JSON нельзя разобрать вообще — бросает ValueError.
    """
    raw_json = _extract_json_object(text.strip())
    try:
        data: dict = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Не удалось разобрать JSON из ответа модели: {exc}") from exc

    params = ScoreParams(
        **{name: _coerce_unit(data.get(name)) for name in PARAM_NAMES}  # type: ignore[arg-type]
    )

    confidence = _coerce_unit(data.get("confidence"))

    raw_rationale = data.get("rationale")
    rationale: str | None = None
    if raw_rationale is not None:
        rationale = str(raw_rationale).strip()
        if len(rationale) > _RATIONALE_MAX_CHARS:
            rationale = rationale[:_RATIONALE_MAX_CHARS]
        if not rationale:
            rationale = None

    return ScoreResult(params=params, confidence=confidence, rationale=rationale)
