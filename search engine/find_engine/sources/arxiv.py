"""Плагин источника arXiv: загрузка статей через Atom API."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import feedparser
import httpx

from find_engine.config import Settings
from find_engine.core.models import Item, RawRecord
from find_engine.sources.http import request_with_retry

logger = logging.getLogger(__name__)

_ARXIV_API = "http://export.arxiv.org/api/query"
_MAX_RESULTS = 50


def _safe_dict(entry: Any) -> dict[str, Any]:
    """Конвертировать feedparser-entry в JSON-совместимый dict."""
    result: dict[str, Any] = {}
    for key, value in entry.items():
        if isinstance(value, time.struct_time):
            result[key] = datetime(*value[:6], tzinfo=timezone.utc).isoformat()
        elif isinstance(value, list):
            result[key] = [
                _safe_dict(v) if hasattr(v, "items") else
                datetime(*v[:6], tzinfo=timezone.utc).isoformat() if isinstance(v, time.struct_time) else v
                for v in value
            ]
        elif hasattr(value, "items"):
            result[key] = _safe_dict(value)
        else:
            result[key] = value
    return result


def _parse_arxiv_id(raw_id: str) -> str:
    """Извлечь стабильный ID из URL вида http://arxiv.org/abs/2403.09000v1."""
    arxiv_id = raw_id.rsplit("/", 1)[-1]
    if "v" in arxiv_id and arxiv_id[-1].isdigit():
        arxiv_id = arxiv_id.rsplit("v", 1)[0]
    return arxiv_id


class ArxivSource:
    """Источник статей из arXiv через Atom API."""

    name = "arxiv"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _entry_to_raw(self, entry: Any) -> RawRecord:
        """Преобразовать feedparser-entry в RawRecord."""
        raw_id = entry.get("id", "")
        external_id = _parse_arxiv_id(raw_id)
        return RawRecord(
            source=self.name,
            external_id=external_id,
            payload=_safe_dict(entry),
        )

    async def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]:
        categories = self._settings.arxiv_category_list
        query = " OR ".join(f"cat:{c}" for c in categories)
        start = int(cursor) if cursor else 0

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            params = {
                "search_query": query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "start": start,
                "max_results": _MAX_RESULTS,
            }
            resp = await request_with_retry(
                client, "GET", _ARXIV_API,
                max_retries=self._settings.http_max_retries,
                params=params,
            )

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            published = entry.get("published_parsed")
            if since is not None and published is not None:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt <= since:
                    continue
            yield self._entry_to_raw(entry)

    def normalize(self, raw: RawRecord) -> Item:
        """Привести RawRecord к нормализованной модели Item."""
        p = raw.payload

        title = " ".join(p.get("title", "").split())

        link = p.get("link", "")
        if not link:
            links = p.get("links", [])
            for lnk in links:
                if isinstance(lnk, dict) and lnk.get("rel") == "alternate":
                    link = lnk.get("href", "")
                    break
            if not link and links:
                first = links[0]
                link = first.get("href", "") if isinstance(first, dict) else ""

        authors = p.get("authors", [])
        if authors and isinstance(authors[0], dict):
            author = authors[0].get("name")
        else:
            author = p.get("author") or None

        tags: list[str] = []
        for tag in p.get("tags", []):
            term = tag.get("term") if isinstance(tag, dict) else None
            if term:
                tags.append(term)

        created_at: datetime | None = None
        published_str = p.get("published")
        if published_str:
            try:
                from email.utils import parsedate_to_datetime
                created_at = parsedate_to_datetime(published_str)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
            except Exception:
                pass
        if created_at is None:
            published_parsed = p.get("published_parsed")
            if published_parsed and isinstance(published_parsed, str):
                try:
                    created_at = datetime.fromisoformat(published_parsed)
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

        return Item(
            source=self.name,
            external_id=raw.external_id,
            title=title,
            url=link,
            author=author,
            body=p.get("summary"),
            score=None,
            tags=tags,
            created_at=created_at,
        )
