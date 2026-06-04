# Ядро парсинга «find-engine» — план реализации (v1)

## Контекст

Нужно собирать данные о новых идеях/проектах в сфере ИИ и IT из публичных
источников в единую базу. Само ядро **только собирает** данные — аналитику и
поиск конкурентов делает отдельный софт поверх этой базы.

Решения, принятые на этапе brainstorming:
- **Назначение:** парсинг + сбор в базу. Без встроенной аналитики.
- **Источники v1:** GitHub, Reddit, Hacker News, arXiv (все с API/RSS — легально и чисто).
- **Источники v2:** произвольные форумы с HTML-парсингом (Discourse, vBulletin, блоги).
- **Стек:** Python + PostgreSQL (pgvector подключим позже для семантического поиска).
- **Запуск:** управление через HTTP API (FastAPI) — принудительный запуск задач + cron-расписание.
- **Модель данных:** гибрид — общая таблица `items` для поиска/аналитики + сырые
  таблицы по источникам (`raw_records`) для деталей.

## Архитектура (слои)

```
API (FastAPI)        POST /jobs, GET /jobs/{id}, GET /health
   │
Scheduler            cron-триггеры → ставят jobs в очередь
   │
Orchestrator         берёт job → запускает нужный Source-плагин → Normalizer → Storage
   │
Sources (плагины)    github / reddit / hackernews / arxiv — общий интерфейс Source
   │
Normalizer           RawRecord → единая модель Item
   │
Storage (repo)       upsert в Postgres, дедуп по (source, external_id)
```

Главный принцип: добавление источника = новый файл-плагин, ядро не меняется.

## Ключевая абстракция — Source

```python
class Source(Protocol):
    name: str
    def fetch(self, since: datetime, cursor: str | None) -> Iterator[RawRecord]: ...
    def normalize(self, raw: RawRecord) -> Item: ...
```

- `fetch(since, cursor)` — инкрементальный добор: тянет только новое с момента
  последнего запуска. `cursor` — для пагинации внутри одного запуска.
- `normalize` — приводит сырой ответ к единой модели `Item`.

## Модель данных (гибрид)

**Таблица `items`** — нормализованное, для поиска/аналитики:
| поле | тип | описание |
|------|-----|----------|
| id | uuid PK | внутренний id |
| source | text | github / reddit / hackernews / arxiv |
| external_id | text | id в источнике |
| title | text | заголовок |
| url | text | ссылка |
| author | text | автор |
| body | text | текст/описание |
| score | int | звёзды/апвоты/нет |
| tags | text[] | темы/языки/категории |
| created_at | timestamptz | дата создания в источнике |
| fetched_at | timestamptz | когда мы забрали |
| UNIQUE(source, external_id) | | для дедупа/upsert |

**Таблица `raw_records`** — полный сырой ответ:
| поле | тип |
|------|-----|
| id | uuid PK |
| item_id | uuid FK → items |
| source | text |
| payload | jsonb |
| fetched_at | timestamptz |

**Таблица `jobs`** — состояние задач сбора:
| поле | тип |
|------|-----|
| id | uuid PK |
| source | text |
| status | text (queued/running/success/failed) |
| since | timestamptz (с какого момента добирали) |
| cursor | text (где остановились — для resume) |
| stats | jsonb (fetched/inserted/skipped) |
| error | text |
| started_at / finished_at | timestamptz |

`jobs` хранит per-source watermark (`since`) → каждый следующий запуск
инкрементален.

## Структура проекта

```
find_engine/
  api/            FastAPI: routers (jobs, health), зависимости
  core/
    models.py     pydantic: Item, RawRecord, JobStatus
    source.py     Source Protocol + RawRecord
    orchestrator.py  прогон job: fetch → normalize → store
    scheduler.py  cron → постановка jobs
  sources/
    github.py     REST/GraphQL: trending/search repos, releases
    reddit.py     subreddits (r/MachineLearning, r/LocalLLaMA, ...)
    hackernews.py Firebase API / Algolia search
    arxiv.py      Atom API (cs.AI, cs.LG, cs.CL)
  storage/
    db.py         подключение (asyncpg/SQLAlchemy)
    repository.py upsert items/raw_records, чтение/запись jobs
    migrations/   Alembic
  config.py       env: DB_URL, API-ключи, cron-расписания
  main.py         точка входа FastAPI
tests/
  test_normalize_<source>.py   фикстуры сырых ответов → проверка Item
  test_repository.py           upsert/дедуп
  test_orchestrator.py         прогон с мок-источником
pyproject.toml
docker-compose.yml  postgres + (опц.) сам сервис
.env.example
README.md
```

## Источники — детали

- **GitHub:** REST `/search/repositories` (сортировка по дате/звёздам, фильтр по
  топикам ai/llm/ml) + `/repos/{}/releases`. Токен из env, уважать rate-limit.
- **Hacker News:** Algolia Search API (`search_by_date`, фильтр по баллам/ключам).
- **Reddit:** публичный JSON-эндпоинт сабреддитов или OAuth-app; список сабов в конфиге.
- **arXiv:** Atom API по категориям, инкремент по дате.

Общее: throttling/backoff на каждый источник, секреты — из env, никаких креденшелов в коде.

## Порядок реализации (TDD)

1. **Каркас + конфиг:** pyproject, config.py, docker-compose с Postgres, `.env.example`.
2. **Модели и схема:** `core/models.py`, Alembic-миграция (items, raw_records, jobs).
3. **Storage:** `repository.py` — upsert + дедуп. Тест `test_repository.py`.
4. **Source-интерфейс + Orchestrator:** прогон с мок-источником. Тест `test_orchestrator.py`.
5. **Источники по одному:** arxiv → hackernews → github → reddit. Для каждого:
   тест нормализации на сохранённой фикстуре сырого ответа, затем `fetch`.
6. **API:** FastAPI — `POST /jobs` (запуск по источнику), `GET /jobs/{id}`, `GET /health`.
7. **Scheduler:** cron (APScheduler) → ставит jobs, watermark из последнего job.

## Верификация

- `pytest` — все unit-тесты (нормализация на фикстурах, upsert/дедуп, orchestrator с моком).
- Локально: `docker-compose up` (Postgres) → `alembic upgrade head` →
  `POST /jobs {"source":"arxiv"}` → проверить, что в `items` и `raw_records`
  появились записи, повторный запуск не плодит дубли (дедуп по
  `(source, external_id)`).
- `GET /jobs/{id}` показывает статус и stats; `GET /health` отвечает.
- Проверить инкрементальность: второй запуск с тем же источником тянет только
  новое (watermark `since` из предыдущего job).

## Явно вне scope v1 (YAGNI)

- Аналитика, дашборды, поиск конкурентов — отдельный софт.
- HTML-парсинг произвольных форумов — v2.
- Семантический поиск/эмбеддинги (pgvector) — позже; схема к этому готова.
