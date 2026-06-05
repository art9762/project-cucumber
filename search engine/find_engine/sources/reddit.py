"""Источник Reddit: выгружает новые посты из заданных сабреддитов через public JSON API."""

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

_BASE_URL = "https://www.reddit.com/r/{subreddit}/new.json"
_PAGE_LIMIT = 100
_MAX_PAGES = 3


class RedditSource:
    """Плагин Reddit. Читает /new для каждого сабреддита из настроек."""

    name = "reddit"

    def __init__(self, settings: Settings) -> None:
        self._subreddits = settings.reddit_subreddit_list
        self._user_agent = settings.reddit_user_agent
        self._timeout = settings.http_timeout
        self._max_retries = settings.http_max_retries

    async def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]:
        headers = {"User-Agent": self._user_agent}
        async with httpx.AsyncClient(timeout=self._timeout, headers=headers, follow_redirects=True) as client:
            for subreddit in self._subreddits:
                async for record in self._fetch_subreddit(client, subreddit, since):
                    yield record

    async def _fetch_subreddit(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
        since: datetime | None,
    ) -> AsyncIterator[RawRecord]:
        url = _BASE_URL.format(subreddit=subreddit)
        params: dict[str, Any] = {"limit": _PAGE_LIMIT}

        for _page in range(_MAX_PAGES):
            resp = await request_with_retry(
                client, "GET", url, max_retries=self._max_retries, params=params
            )
            data = resp.json()["data"]
            children = data.get("children", [])

            for child in children:
                post = child["data"]
                if since is not None:
                    created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)
                    if created <= since:
                        return
                yield RawRecord(
                    source="reddit",
                    external_id=post["id"],
                    payload=post,
                )

            after = data.get("after")
            if not after:
                break
            params = {"limit": _PAGE_LIMIT, "after": after}

    def normalize(self, raw: RawRecord) -> Item:
        post = raw.payload
        url = post.get("url") or f"https://www.reddit.com{post['permalink']}"
        tags = [post["subreddit"]]
        if post.get("link_flair_text"):
            tags.append(post["link_flair_text"])
        return Item(
            source="reddit",
            external_id=post["id"],
            title=post["title"],
            url=url,
            author=post.get("author"),
            body=post.get("selftext") or None,
            score=post.get("score"),
            tags=tags,
            created_at=datetime.fromtimestamp(post["created_utc"], tz=timezone.utc),
        )
