"""Построение промпта веб-ресёрча и парсинг ответа модели (Фаза 3).

Чистые функции без I/O: только строки, JSON, регулярные выражения.
Используется оркестратором ресёрча для вызова TrinityClient.search_complete.
"""

from __future__ import annotations

import json
import re
from typing import Any

from analysis.research.models import Competitor, ResearchResult
from analysis.storage.orm import ItemReadORM

# Максимальная длина тела item в промпте (символов) — чтобы промпт оставался дешёвым.
_BODY_MAX_CHARS = 2000


def build_research_prompt(
    item: ItemReadORM,
    category_title: str | None = None,
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для TrinityClient.search_complete(...).

    Просит модель с помощью веб-поиска разобрать идею: что это, насколько тема
    горячая и зрелая, какие есть конкуренты/похожие продукты (с URL). Требует
    строгий JSON: summary (~абзац), competitors (список {name,url,note}),
    maturity_signal 0..1, potential_signal 0..1, confidence 0..1.
    Тело item обрезается до ~2000 символов.
    """
    category_hint = (
        f" Материал относится к категории: «{category_title}»."
        if category_title
        else ""
    )

    system_prompt = (
        "Ты — аналитик технологических идей и стартапов."
        f"{category_hint}"
        " Используй веб-поиск, чтобы детально разобрать переданную идею:\n"
        "  1. Что это такое и как работает.\n"
        "  2. Насколько тема горячая и актуальная прямо сейчас.\n"
        "  3. Насколько рынок уже насыщен готовыми решениями.\n"
        "  4. Какие конкуренты и похожие продукты существуют (название + URL).\n\n"
        "После веб-поиска верни СТРОГИЙ JSON-объект:\n"
        "  - \"summary\": краткий аналитический абзац (~3–5 предложений).\n"
        "  - \"competitors\": массив объектов {\"name\": \"...\", \"url\": \"...\","
        " \"note\": \"...\"} — ближайшие аналоги и конкуренты с URL.\n"
        "  - \"maturity_signal\": число 0.0–1.0 (1.0 = рынок очень насыщен).\n"
        "  - \"potential_signal\": число 0.0–1.0 (1.0 = огромный потенциал).\n"
        "  - \"confidence\": число 0.0–1.0 (уверенность в оценке).\n\n"
        "Правила ответа:\n"
        "1. Отвечай ТОЛЬКО валидным JSON-объектом — без пояснений, без ```-блоков.\n"
        "2. \"summary\" обязателен и не должен быть пустым.\n"
        "3. \"competitors\" может быть пустым массивом [], если аналогов не найдено.\n"
        "Пример: {\"summary\": \"Платформа для...\", \"competitors\":"
        " [{\"name\": \"Foo\", \"url\": \"https://foo.io\","
        " \"note\": \"ближайший аналог\"}],"
        " \"maturity_signal\": 0.6, \"potential_signal\": 0.7, \"confidence\": 0.8}"
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
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

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


def _coerce_unit_or_none(raw: Any) -> float | None:
    """Привести значение к float в [0.0, 1.0] или вернуть None при ошибке/отсутствии."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, value))


def _coerce_confidence(raw: Any) -> float:
    """Привести значение к float в [0.0, 1.0]; при ошибке вернуть 0.5."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, value))


def _parse_competitors(raw: Any) -> list[Competitor]:
    """Разобрать список конкурентов; записи без name отбрасываются."""
    if not isinstance(raw, list):
        return []
    result: list[Competitor] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        raw_name = entry.get("name")
        if not raw_name or not str(raw_name).strip():
            continue
        name = str(raw_name).strip()
        raw_url = entry.get("url")
        url = str(raw_url).strip() if raw_url and str(raw_url).strip() else None
        raw_note = entry.get("note")
        note = str(raw_note).strip() if raw_note and str(raw_note).strip() else None
        result.append(Competitor(name=name, url=url, note=note))
    return result


def parse_research(text: str, sources: list[str]) -> ResearchResult:
    """Разобрать JSON-ответ модели (raw / ```-блок / проза по краям).

    summary: обязателен (пусто/отсутствует → ValueError).
    competitors: list[Competitor] (без name — пропускаются).
    maturity_signal / potential_signal: float|None, кламп [0,1].
    confidence: float, кламп [0,1], дефолт 0.5.
    sources прокидываются в ResearchResult.sources; URL конкурентов
    добавляются, если их ещё нет в sources.
    """
    raw_json = _extract_json_object(text.strip())
    try:
        data: dict = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Не удалось разобрать JSON из ответа модели: {exc}") from exc

    raw_summary = data.get("summary")
    if not raw_summary or not str(raw_summary).strip():
        raise ValueError("Ответ модели не содержит обязательного поля 'summary'.")
    summary = str(raw_summary).strip()

    competitors = _parse_competitors(data.get("competitors"))
    maturity_signal = _coerce_unit_or_none(data.get("maturity_signal"))
    potential_signal = _coerce_unit_or_none(data.get("potential_signal"))
    confidence = _coerce_confidence(data.get("confidence"))

    merged_sources = list(sources)
    existing = set(merged_sources)
    for comp in competitors:
        if comp.url and comp.url not in existing:
            merged_sources.append(comp.url)
            existing.add(comp.url)

    return ResearchResult(
        summary=summary,
        competitors=competitors,
        sources=merged_sources,
        maturity_signal=maturity_signal,
        potential_signal=potential_signal,
        confidence=confidence,
    )
