"""Построение промпта классификации и парсинг ответа модели.

Чистые функции без I/O: только строки, JSON, регулярные выражения.
Используется оркестратором (:mod:`analysis.classify.classifier`) для вызова Trinity.
"""

from __future__ import annotations

import json
import re
from typing import Any

from analysis.classify.models import CategoryNode, ClassificationResult
from analysis.storage.orm import ItemReadORM

# Максимальная длина тела item в промпте (символов) — чтобы промпт оставался дешёвым.
_BODY_MAX_CHARS = 2000


def _to_kebab(value: str) -> str:
    """Нормализовать строку в kebab-case ASCII.

    Шаги: lowercase → пробелы/подчёркивания → дефис → оставить [a-z0-9-] → убрать
    повторные дефисы → trim дефисов по краям.
    """
    s = value.lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    s = re.sub(r"-{2,}", "-", s)
    return s.strip("-")


def build_classify_prompt(
    item: ItemReadORM,
    categories: list[CategoryNode],
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для TrinityClient.complete(messages, system=...).

    - Перечисляет переданные категории (slug + title) в system prompt.
    - Инструктирует модель выбрать РОВНО ОДИН существующий slug, указать
      confidence 0..1 и ОПЦИОНАЛЬНО предложить одну новую подкатегорию.
    - Требует строгий JSON-ответ:
      {"category": "<slug>", "confidence": <0..1>,
       "suggested_subcategory": {"slug": "...", "title": "..."} | null}
    - messages = [{"role":"user","content": <title/body/url/source в виде текста>}].
    - Длинное тело item обрезается до ~2000 символов.
    """
    category_lines = "\n".join(f"  - {c.slug}: {c.title}" for c in categories)
    system_prompt = (
        "Ты — классификатор контента. Твоя задача — выбрать РОВНО ОДНУ категорию"
        " из списка ниже, которая лучше всего описывает переданный материал.\n\n"
        f"Доступные категории:\n{category_lines}\n\n"
        "Правила ответа:\n"
        "1. Отвечай ТОЛЬКО валидным JSON-объектом — без пояснений, без ```-блоков.\n"
        "2. Поле \"category\": slug одной из перечисленных категорий (строго из списка).\n"
        "3. Поле \"confidence\": число от 0.0 до 1.0.\n"
        "4. Поле \"suggested_subcategory\": объект {\"slug\": \"...\", \"title\": \"...\"}"
        " с предложением новой подкатегории, или null.\n"
        "Пример: {\"category\": \"ai\", \"confidence\": 0.9,"
        " \"suggested_subcategory\": {\"slug\": \"llm-agents\", \"title\": \"LLM-агенты\"}}"
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


def _coerce_confidence(raw: Any) -> float:
    """Привести значение к float в диапазоне [0.0, 1.0]; при ошибке вернуть 0.5."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def parse_classification(text: str) -> ClassificationResult:
    """Разобрать ответ модели (JSON, возможно в ```-блоке или с мусором по краям).

    - Принимает чистый JSON, JSON в ```json-блоке, JSON с прозой вокруг него.
    - confidence: приводится к float, клампится в [0.0, 1.0]; при отсутствии/ошибке — 0.5.
    - suggested_subcategory: если задан частично (только slug или только title) — оба None.
      slug нормализуется в kebab-case ASCII.
    - Требует непустой 'category' → ClassificationResult.category_slug (нормализуется).
    - Если 'category' отсутствует или пустой — бросает ValueError.
    """
    raw_json = _extract_json_object(text.strip())
    try:
        data: dict = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Не удалось разобрать JSON из ответа модели: {exc}") from exc

    raw_category = data.get("category")
    if not raw_category or not str(raw_category).strip():
        raise ValueError("Ответ модели не содержит обязательного поля 'category'.")

    category_slug = _to_kebab(str(raw_category).strip())
    if not category_slug:
        raise ValueError("Поле 'category' не содержит допустимых символов после нормализации.")

    confidence = _coerce_confidence(data.get("confidence"))

    sub_slug: str | None = None
    sub_title: str | None = None
    suggestion = data.get("suggested_subcategory")
    if suggestion and isinstance(suggestion, dict):
        raw_sub_slug = suggestion.get("slug")
        raw_sub_title = suggestion.get("title")
        has_slug = bool(raw_sub_slug and str(raw_sub_slug).strip())
        has_title = bool(raw_sub_title and str(raw_sub_title).strip())
        if has_slug and has_title:
            sub_slug = _to_kebab(str(raw_sub_slug).strip())
            sub_title = str(raw_sub_title).strip()
        # Если только одно из двух — оба остаются None (partial → discard)

    return ClassificationResult(
        category_slug=category_slug,
        confidence=confidence,
        suggested_subcategory_slug=sub_slug,
        suggested_subcategory_title=sub_title,
    )
