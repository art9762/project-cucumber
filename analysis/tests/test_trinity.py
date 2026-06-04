"""Юнит-тесты TrinityClient — полностью герметичные (сеть не используется).

Паттерн: Settings создаётся явно с тестовыми значениями, реальный Anthropic-клиент
заменяется AsyncMock, env-переменные окружения не читаются.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysis.config import Settings
from analysis.trinity import TrinityClient, get_trinity_client


def _make_settings(
    token: str | None = "test-token",
    base_url: str = "https://test.gateway/v1",
    cheap: str = "cheap-model",
    deep: str = "deep-model",
) -> Settings:
    """Создать изолированные Settings, не читая .env или окружение."""
    return Settings(
        anthropic_auth_token=token,
        anthropic_base_url=base_url,
        analysis_model_cheap=cheap,
        analysis_model_deep=deep,
        db_url_analysis="sqlite+aiosqlite:///:memory:",
        db_url_read="sqlite+aiosqlite:///:memory:",
    )


def _make_response(*texts: str) -> MagicMock:
    """Создать фиктивный объект ответа с текстовыми блоками."""
    content = [SimpleNamespace(text=t) for t in texts]
    response = MagicMock()
    response.content = content
    return response


class TestTrinityClientConstruction:
    """Проверяем, что клиент создаётся с правильными параметрами."""

    def test_stores_cheap_and_deep_models(self) -> None:
        with patch("anthropic.AsyncAnthropic"):
            client = TrinityClient(_make_settings(cheap="haiku", deep="sonnet"))
        assert client._model_cheap == "haiku"
        assert client._model_deep == "sonnet"

    def test_constructs_async_anthropic_with_correct_args(self) -> None:
        with patch("analysis.trinity.anthropic.AsyncAnthropic") as mock_cls:
            TrinityClient(_make_settings(token="my-token", base_url="https://gw/"))
        mock_cls.assert_called_once_with(api_key="my-token", base_url="https://gw/")

    def test_constructs_with_empty_token_when_none(self) -> None:
        with patch("analysis.trinity.anthropic.AsyncAnthropic") as mock_cls:
            TrinityClient(_make_settings(token=None))
        mock_cls.assert_called_once_with(api_key="", base_url="https://test.gateway/v1")


class TestIsConfigured:
    """Проверяем свойство is_configured."""

    def test_true_when_token_present(self) -> None:
        with patch("anthropic.AsyncAnthropic"):
            client = TrinityClient(_make_settings(token="abc"))
        assert client.is_configured is True

    def test_false_when_token_none(self) -> None:
        with patch("anthropic.AsyncAnthropic"):
            client = TrinityClient(_make_settings(token=None))
        assert client.is_configured is False

    def test_false_when_token_empty_string(self) -> None:
        with patch("anthropic.AsyncAnthropic"):
            client = TrinityClient(_make_settings(token=""))
        assert client.is_configured is False


class TestComplete:
    """Проверяем метод complete()."""

    def _build_client(self) -> tuple[TrinityClient, AsyncMock]:
        mock_messages_create = AsyncMock(return_value=_make_response("Hello", " world"))
        mock_messages = MagicMock()
        mock_messages.create = mock_messages_create
        mock_anthropic = MagicMock()
        mock_anthropic.messages = mock_messages

        with patch("analysis.trinity.anthropic.AsyncAnthropic", return_value=mock_anthropic):
            client = TrinityClient(_make_settings())

        return client, mock_messages_create

    async def test_returns_concatenated_text(self) -> None:
        client, _ = self._build_client()
        result = await client.complete([{"role": "user", "content": "hi"}])
        assert result == "Hello world"

    async def test_uses_cheap_model_by_default(self) -> None:
        client, mock_create = self._build_client()
        await client.complete([{"role": "user", "content": "hi"}])
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "cheap-model"

    async def test_uses_passed_model_when_overridden(self) -> None:
        client, mock_create = self._build_client()
        await client.complete([{"role": "user", "content": "hi"}], model="deep-model")
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "deep-model"

    async def test_passes_max_tokens(self) -> None:
        client, mock_create = self._build_client()
        await client.complete([{"role": "user", "content": "hi"}], max_tokens=512)
        assert mock_create.call_args.kwargs["max_tokens"] == 512

    async def test_passes_system_when_provided(self) -> None:
        client, mock_create = self._build_client()
        await client.complete(
            [{"role": "user", "content": "hi"}], system="You are helpful."
        )
        assert mock_create.call_args.kwargs["system"] == "You are helpful."

    async def test_omits_system_when_none(self) -> None:
        client, mock_create = self._build_client()
        await client.complete([{"role": "user", "content": "hi"}])
        assert "system" not in mock_create.call_args.kwargs

    async def test_single_text_block(self) -> None:
        mock_create = AsyncMock(return_value=_make_response("Only one"))
        mock_messages = MagicMock()
        mock_messages.create = mock_create
        mock_anthropic = MagicMock()
        mock_anthropic.messages = mock_messages

        with patch("analysis.trinity.anthropic.AsyncAnthropic", return_value=mock_anthropic):
            client = TrinityClient(_make_settings())

        result = await client.complete([{"role": "user", "content": "ping"}])
        assert result == "Only one"


class TestGetTrinityClientSingleton:
    """Проверяем модульный singleton get_trinity_client()."""

    def test_returns_trinity_client_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import analysis.trinity as trinity_module

        monkeypatch.setattr(trinity_module, "_trinity_client", None)
        with patch("analysis.trinity.anthropic.AsyncAnthropic"):
            with patch("analysis.trinity.get_settings", return_value=_make_settings()):
                result = get_trinity_client()
        assert isinstance(result, TrinityClient)

    def test_returns_same_instance_on_second_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import analysis.trinity as trinity_module

        monkeypatch.setattr(trinity_module, "_trinity_client", None)
        with patch("analysis.trinity.anthropic.AsyncAnthropic"):
            with patch("analysis.trinity.get_settings", return_value=_make_settings()):
                first = get_trinity_client()
                second = get_trinity_client()
        assert first is second
