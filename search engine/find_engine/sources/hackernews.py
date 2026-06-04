"""Источник Hacker News через Algolia HN Search API.

Тянет истории (stories) по заданному запросу с фильтрацией по очкам.
Поддерживает инкрементальный добор через параметр `since`.
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

_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search_by_date"
_MAX_PAGES = 5


class HackerNewsSource:
    """Источник Hacker News (Algolia HN Search API)."""

    name = "hackernews"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]:
        params: dict[str, Any] = {
            "query": self._settings.hn_query,
            "tags": "story",
            "numericFilters": f"points>={self._settings.hn_min_points}",
            "hitsPerPage": 20,
        }
        if since is not None:
            unix_ts = int(since.timestamp())
            params["numericFilters"] += f",created_at_i>{unix_ts}"

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            for page in range(_MAX_PAGES):
                params["page"] = page
                resp = await request_with_retry(
                    client,
                    "GET",
                    _ALGOLIA_URL,
                    max_retries=self._settings.http_max_retries,
                    params=params,
                )
                data = resp.json()
                hits: list[dict[str, Any]] = data.get("hits", [])
                nb_pages: int = data.get("nbPages", 1)

                logger.debug(
                    "HN page %d/%d — %d hits", page + 1, nb_pages, len(hits)
                )

                for hit in hits:
                    yield RawRecord(
                        source="hackernews",
                        external_id=str(hit["objectID"]),
                        payload=hit,
                    )

                if page + 1 >= nb_pages:
                    break

    def normalize(self, raw: RawRecord) -> Item:
        hit = raw.payload
        object_id = str(hit["objectID"])
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
        tags = [t for t in hit.get("_tags", []) if isinstance(t, str)]
        created_at: datetime | None = None
        raw_ts = hit.get("created_at")
        if raw_ts:
            created_at = datetime.fromisoformat(
                raw_ts.replace("Z", "+00:00")
            ).astimezone(timezone.utc)

        return Item(
            source="hackernews",
            external_id=object_id,
            title=hit["title"],
            url=url,
            author=hit.get("author"),
            score=hit.get("points"),
            body=hit.get("story_text"),
            tags=tags,
            created_at=created_at,
        )
