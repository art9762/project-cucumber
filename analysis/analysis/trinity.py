"""Тонкая обёртка над Anthropic SDK, направленная на шлюз Trinity.

Паттерн singleton повторяет db.py: модульный глобал + get_trinity_client().
"""

from __future__ import annotations

import anthropic

from analysis.config import Settings, get_settings

_trinity_client: TrinityClient | None = None


class TrinityClient:
    """Async-клиент для обращений к Trinity (Anthropic-совместимый шлюз)."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Инициализация клиента.

        Args:
            settings: Явные настройки; если None — используется get_settings().
        """
        cfg = settings if settings is not None else get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=cfg.anthropic_auth_token or "",
            base_url=cfg.anthropic_base_url,
        )
        self._model_cheap = cfg.analysis_model_cheap
        self._model_deep = cfg.analysis_model_deep
        self._token: str | None = cfg.anthropic_auth_token

    @property
    def is_configured(self) -> bool:
        """True, если токен авторизации задан и не пуст."""
        return bool(self._token)

    async def complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        system: str | None = None,
    ) -> str:
        """Отправить сообщения в LLM и вернуть сконкатенированный текст ответа.

        Args:
            messages: История сообщений в формате Anthropic Messages API.
            model: Имя модели; по умолчанию — дешёвая (cheap).
            max_tokens: Максимальное число токенов в ответе.
            system: Системный промпт (опционально).

        Returns:
            Конкатенация текстовых блоков из ответа модели.
        """
        kwargs: dict = {
            "model": model or self._model_cheap,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return "".join(block.text for block in response.content if hasattr(block, "text"))

    async def search_complete(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        max_tokens: int = 2048,
        system: str | None = None,
        max_searches: int = 3,
    ) -> tuple[str, list[str]]:
        """Как ``complete``, но с включённым серверным веб-поиском (Trinity
        прокидывает нативный Anthropic-инструмент ``web_search_20250305``).

        Модель сама решает, искать ли, и сколько раз (до ``max_searches``).
        Возвращает кортеж ``(text, source_urls)``: склейку текстовых блоков
        ответа и список URL источников, на которые ссылался веб-поиск
        (из блоков ``web_search_tool_result``), без дубликатов, в порядке
        появления.

        Args:
            messages: История сообщений (формат Anthropic Messages API).
            model: Имя модели; по умолчанию — дешёвая.
            max_tokens: Лимит токенов ответа.
            system: Системный промпт (опционально).
            max_searches: Максимум обращений к веб-поиску за вызов.

        Returns:
            ``(text, source_urls)``.
        """
        kwargs: dict = {
            "model": model or self._model_cheap,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": [
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_searches,
                }
            ],
        }
        if system is not None:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        sources: list[str] = []
        seen: set[str] = set()
        for block in response.content:
            if getattr(block, "type", None) == "text" and hasattr(block, "text"):
                text_parts.append(block.text)
            elif getattr(block, "type", None) == "web_search_tool_result":
                for result in getattr(block, "content", None) or []:
                    url = getattr(result, "url", None)
                    if isinstance(result, dict):
                        url = result.get("url")
                    if url and url not in seen:
                        seen.add(url)
                        sources.append(url)
        return "".join(text_parts), sources


def get_trinity_client() -> TrinityClient:
    """Вернуть singleton TrinityClient (ленивая инициализация)."""
    global _trinity_client
    if _trinity_client is None:
        _trinity_client = TrinityClient()
    return _trinity_client
