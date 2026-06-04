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


def get_trinity_client() -> TrinityClient:
    """Вернуть singleton TrinityClient (ленивая инициализация)."""
    global _trinity_client
    if _trinity_client is None:
        _trinity_client = TrinityClient()
    return _trinity_client
