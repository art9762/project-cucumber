# Как добавить новый источник

Главный принцип расширяемости find-engine: **новый источник = новый плагин, ядро не меняется**.
Чтобы добавить источник, вы пишете один класс по протоколу `Source` и регистрируете его. Ничего в
`core/`, `storage/` или `api/` править не нужно.

---

## 1. Контракт `Source`

Источник описан протоколом в [`find_engine/core/source.py`](../find_engine/core/source.py):

```python
@runtime_checkable
class Source(Protocol):
    name: str

    def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]: ...

    def normalize(self, raw: RawRecord) -> Item: ...
```

### `name: str`
Уникальный идентификатор источника (например `"hackernews"`). Используется как ключ в реестре,
как значение `Item.source` / `RawRecord.source` и как ключ в `Settings.cron_for(name)`. Должен быть
стабильным: по паре `(source, external_id)` идёт дедуп в БД.

### `fetch(since, cursor) -> AsyncIterator[RawRecord]`
**Асинхронный генератор**, который тянет сырые записи и `yield`-ит их по одной.

- **`since: datetime | None`** — инкрементальность (watermark). Это момент, до которого данные уже
  собраны прошлым запуском. `fetch` должен возвращать **только записи новее `since`**. Если `None` —
  первый запуск, тянем всё доступное. Watermark хранится в `Job.since` и подаётся ядром автоматически.
- **`cursor: str | None`** — пагинация / resume внутри одного запуска. Это непрозрачная для ядра
  строка, смысл которой задаёт сам источник (номер страницы, offset, токен next-page). Хранится в
  `Job.cursor`. Если ваш API отдаёт всё за несколько страниц в одном `fetch` — внутренний цикл по
  страницам достаточен, `cursor` можно игнорировать.

`fetch` отдаёт `RawRecord` — сырой payload as-is, без приведения к общей модели:

```python
class RawRecord(BaseModel):
    source: str
    external_id: str          # стабильный ID записи в рамках источника
    payload: dict[str, Any]   # сырой ответ источника
    fetched_at: datetime | None = None
```

### `normalize(raw) -> Item`
Чистая функция (без сети): `RawRecord.payload` → нормализованный `Item`:

```python
class Item(BaseModel):
    source: str               # обязательно, == self.name
    external_id: str          # обязательно, стабильный и уникальный в рамках источника
    title: str                # обязательно
    url: str                  # обязательно
    author: str | None = None # опционально
    body: str | None = None
    score: int | None = None
    tags: list[str] = []
    created_at: datetime | None = None
    fetched_at: datetime | None = None
```

Обязательные поля: `source`, `external_id`, `title`, `url`. Остальные — опциональны.

---

## 2. Пошаговый рецепт

### Шаг 1. Создать файл плагина
`find_engine/sources/<name>.py` с классом-источником. Конструктор принимает `Settings`:

```python
from find_engine.config import Settings

class MySource:
    name = "mysource"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
```

### Шаг 2. Реализовать `fetch`
Используйте общий HTTP-клиент [`request_with_retry`](../find_engine/sources/http.py) — он сам
уважает таймаут, делает экспоненциальный backoff и обрабатывает `429/5xx` и `Retry-After`. Не
дублируйте throttling в плагине.

```python
import httpx
from find_engine.sources.http import request_with_retry

async def fetch(self, since, cursor):
    page = int(cursor) if cursor else 0
    async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
        while True:
            resp = await request_with_retry(
                client, "GET", API_URL,
                max_retries=self._settings.http_max_retries,
                params={"page": page, "q": self._settings.my_query},
            )
            data = resp.json()
            items = data.get("items", [])
            for it in items:
                # since — отсечение уже собранного (инкрементальность)
                if since is not None and _created(it) <= since:
                    continue
                yield RawRecord(
                    source=self.name,
                    external_id=str(it["id"]),
                    payload=it,
                )
            page += 1
            if not data.get("has_next") or page >= MAX_PAGES:
                break
```

### Шаг 3. Реализовать `normalize`
Достаём поля из `raw.payload`, заполняем `Item`. Без сети. Аккуратно с датами — приводите к UTC:

```python
from datetime import datetime, timezone

def normalize(self, raw):
    p = raw.payload
    created = None
    if p.get("created_at"):
        created = datetime.fromisoformat(
            p["created_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    return Item(
        source=self.name,
        external_id=raw.external_id,
        title=p["title"],
        url=p["html_url"],
        author=p.get("author"),
        body=p.get("text"),
        score=p.get("score"),
        tags=p.get("labels", []),
        created_at=created,
    )
```

### Шаг 4. Добавить настройки (если нужно)
В [`find_engine/config.py`](../find_engine/config.py) добавьте поля в `Settings`. **Секреты —
только сюда, никогда в код.** При желании добавьте cron-расписание и зарегистрируйте его в `cron_for`:

```python
class Settings(BaseSettings):
    ...
    my_query: str = "ai"
    my_api_token: str | None = None    # секрет — читается из .env
    cron_mysource: str = ""            # "" отключает расписание

    def cron_for(self, source: str) -> str:
        return {
            ...
            "mysource": self.cron_mysource,
        }.get(source, "")
```

И продублируйте новые ключи в `.env.example`:

```dotenv
MY_QUERY=ai
MY_API_TOKEN=
CRON_MYSOURCE=
```

### Шаг 5. Зарегистрировать в `register_all`
В [`find_engine/sources/__init__.py`](../find_engine/sources/__init__.py) импортируйте класс и
создайте инстанс:

```python
def register_all(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    ...
    from find_engine.sources.mysource import MySource
    register(MySource(settings))
```

### Шаг 6. Написать тесты нормализации
Положите фикстуру сырого ответа в `tests/fixtures/mysource_search.json` и тестируйте `normalize`
**без сети** (паттерн из `tests/test_normalize_hackernews.py`):

```python
import json
from datetime import timezone
from pathlib import Path

from find_engine.config import Settings
from find_engine.core.models import RawRecord
from find_engine.sources.mysource import MySource

FIXTURES = Path(__file__).parent / "fixtures"


def _load() -> dict:
    return json.loads((FIXTURES / "mysource_search.json").read_text(encoding="utf-8"))


def _make_source() -> MySource:
    return MySource(Settings())


class TestMySourceNormalize:
    def test_normalize_full(self) -> None:
        it = _load()["items"][0]
        raw = RawRecord(source="mysource", external_id=str(it["id"]), payload=it)
        item = _make_source().normalize(raw)

        assert item.source == "mysource"
        assert item.external_id == str(it["id"])
        assert item.title
        assert item.url.startswith("http")
        if item.created_at is not None:
            assert item.created_at.tzinfo == timezone.utc
```

---

## 3. Полный пример минимального источника

Вымышленный источник `example` — забирает посты из JSON-API с пагинацией по странице,
инкрементальностью по `created_at` и нормализацией в `Item`.

```python
# find_engine/sources/example.py
"""Пример минимального источника: JSON-API с пагинацией и инкрементальным добором."""

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

_API_URL = "https://api.example.com/v1/posts"
_MAX_PAGES = 5
_PER_PAGE = 50


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class ExampleSource:
    """Источник example (демонстрационный)."""

    name = "example"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]:
        headers: dict[str, str] = {}
        # секрет берём из Settings, не из кода
        if self._settings.example_token:
            headers["Authorization"] = f"Bearer {self._settings.example_token}"

        start_page = int(cursor) if cursor else 1

        async with httpx.AsyncClient(timeout=self._settings.http_timeout) as client:
            for page in range(start_page, start_page + _MAX_PAGES):
                resp = await request_with_retry(
                    client,
                    "GET",
                    _API_URL,
                    max_retries=self._settings.http_max_retries,
                    headers=headers,
                    params={
                        "query": self._settings.example_query,
                        "page": page,
                        "per_page": _PER_PAGE,
                        "sort": "new",
                    },
                )
                data = resp.json()
                posts: list[dict[str, Any]] = data.get("posts", [])
                logger.debug("example page %d — %d posts", page, len(posts))

                for post in posts:
                    created = _parse_dt(post.get("created_at"))
                    # инкрементальность: пропускаем уже собранное
                    if since is not None and created is not None and created <= since:
                        continue
                    yield RawRecord(
                        source=self.name,
                        external_id=str(post["id"]),
                        payload=post,
                    )

                if not data.get("has_more") or len(posts) < _PER_PAGE:
                    break

    def normalize(self, raw: RawRecord) -> Item:
        p = raw.payload
        post_id = str(p["id"])
        return Item(
            source=self.name,
            external_id=post_id,
            title=p["title"],
            url=p.get("url") or f"https://example.com/p/{post_id}",
            author=p.get("author"),
            body=p.get("text"),
            score=p.get("upvotes"),
            tags=[t for t in p.get("tags", []) if isinstance(t, str)],
            created_at=_parse_dt(p.get("created_at")),
        )
```

Регистрация и настройки для примера:

```python
# find_engine/sources/__init__.py
from find_engine.sources.example import ExampleSource
register(ExampleSource(settings))
```

```python
# find_engine/config.py — поля в Settings
example_query: str = "ai"
example_token: str | None = None
cron_example: str = ""
# и добавить "example": self.cron_example в cron_for()
```

---

## 4. Чек-лист

- [ ] `name` уникален и стабилен; совпадает со значением `source` в `RawRecord` и `Item`.
- [ ] `external_id` **стабильный и уникальный в рамках источника** — не зависит от страницы/времени
      запроса. От него зависит дедуп; нестабильный ID = дубликаты в БД. (См. `_parse_arxiv_id` в
      `arxiv.py`: версионный суффikс `v1/v2` отрезается, чтобы ID был стабильным.)
- [ ] `fetch` — `async`-генератор (`yield`, не `return [...]`).
- [ ] Все HTTP-запросы идут через `request_with_retry` — это уважает rate limits, `429/5xx`,
      `Retry-After` и таймаут из `Settings`.
- [ ] `since` корректно отсекает старые записи (инкрементальность); при `since is None` тянем всё.
- [ ] Обязательные поля `Item`: `source`, `external_id`, `title`, `url` заполнены.
- [ ] Даты приведены к UTC (`astimezone(timezone.utc)` / tz-aware).
- [ ] Секреты только через `Settings` (и `.env.example`), никогда в коде.
- [ ] Источник зарегистрирован в `register_all`.
- [ ] Есть фикстура и unit-тесты `normalize` без сети.

---

## 5. Важные нюансы

- **Дедуп идёт по `(source, external_id)`.** Это уникальный ключ записи в БД. Поэтому `external_id`
  должен быть детерминированным: один и тот же объект источника всегда даёт один и тот же ID.
- **`fetch` — асинхронный генератор.** Ядро итерирует его лениво и upsert-ит записи по мере
  поступления; не собирайте весь список в память и не используйте `return` со списком.
- **`normalize` не ходит в сеть.** Это чистое преобразование `payload → Item`, что и делает его
  легко тестируемым на фикстурах.
- **Никаких хардкоженных секретов.** Токены и ключи читаются только из `Settings` (которые тянут их
  из окружения/`.env`). В код секреты не попадают, в `.env.example` кладётся пустой плейсхолдер.
- **`cursor` непрозрачен для ядра.** Его формат полностью на усмотрение источника; ядро лишь хранит
  и возвращает строку для resume/пагинации.
