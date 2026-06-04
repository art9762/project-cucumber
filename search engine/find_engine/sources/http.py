"""Общий HTTP-клиент для источников: таймаут, повторы с экспоненциальным backoff.

Уважает Retry-After и 429/5xx. Источники используют его, чтобы не дублировать
throttling/backoff в каждом плагине.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    """Выполнить запрос с повторами. Возвращает успешный Response или поднимает последнюю ошибку."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code in _RETRY_STATUS and attempt < max_retries:
                delay = _retry_delay(resp, attempt)
                logger.warning("HTTP %s on %s, retry in %.1fs", resp.status_code, url, delay)
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            delay = 2.0**attempt
            logger.warning("HTTP error on %s (%s), retry in %.1fs", url, exc, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    return 2.0**attempt
