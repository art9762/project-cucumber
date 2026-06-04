"""Источник GitHub: поиск репозиториев по топикам через REST Search API.

Инкрементальный добор через `pushed:>=YYYY-MM-DD`. Пагинация до 3 страниц.
Авторизация опциональна; без токена действует anonymous rate-limit (10 req/min).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx

from find_engine.config import Settings
from find_engine.core.models import Item, RawRecord
from find_engine.sources.http import request_with_retry

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.github.com/search/repositories"
_PER_PAGE = 30
_MAX_PAGES = 3


class GithubSource:
    """Источник GitHub Search API: репозитории по топикам."""

    name = "github"

    def __init__(self, settings: Settings) -> None:
        self._topics: list[str] = settings.github_topic_list
        self._token: str | None = settings.github_token
        self._timeout: float = settings.http_timeout
        self._max_retries: int = settings.http_max_retries

    def _build_query(self, since: datetime | None) -> str:
        parts = [f"topic:{t}" for t in self._topics]
        if since:
            parts.append(f"pushed:>={since.date().isoformat()}")
        return " ".join(parts)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]:
        return self._fetch_pages(since)

    async def _fetch_pages(
        self, since: datetime | None
    ) -> AsyncIterator[RawRecord]:
        q = self._build_query(since)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for page in range(1, _MAX_PAGES + 1):
                params: dict[str, Any] = {
                    "q": q,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": _PER_PAGE,
                    "page": page,
                }
                resp = await request_with_retry(
                    client,
                    "GET",
                    _SEARCH_URL,
                    max_retries=self._max_retries,
                    headers=self._headers(),
                    params=params,
                )
                data = resp.json()
                items: list[dict[str, Any]] = data.get("items", [])
                logger.debug("GitHub page %d: %d repos", page, len(items))
                for repo in items:
                    yield RawRecord(
                        source="github",
                        external_id=str(repo["id"]),
                        payload=repo,
                    )
                if len(items) < _PER_PAGE:
                    break

    def normalize(self, raw: RawRecord) -> Item:
        repo = raw.payload
        tags: list[str] = list(repo.get("topics") or [])
        lang = repo.get("language")
        if lang and lang not in tags:
            tags.append(lang)
        created_raw: str | None = repo.get("created_at")
        created_at: datetime | None = None
        if created_raw:
            created_at = datetime.fromisoformat(
                created_raw.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        return Item(
            source="github",
            external_id=str(repo["id"]),
            title=repo["full_name"],
            url=repo["html_url"],
            author=repo["owner"]["login"],
            body=repo.get("description"),
            score=repo.get("stargazers_count"),
            tags=tags,
            created_at=created_at,
        )
