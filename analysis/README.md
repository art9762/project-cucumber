# analysis — модуль анализа идей

Сервис анализа поверх движка сбора (`../search engine/`). Движок собирает идеи из
публичных источников в Postgres (`items`, `raw_records`, `jobs`); `analysis`
читает эти данные **read-only** и складывает результаты анализа в свои таблицы.

Это **Фаза 0** — рабочий и протестированный каркас. Логики классификации и
скоринга здесь ещё нет (Фазы 1–2). Полная спека: [`../docs/phase-0-analysis-scaffold.md`](../docs/phase-0-analysis-scaffold.md),
общий план: [`../docs/analysis-plan.md`](../docs/analysis-plan.md).

## Что уже есть

- **Конфиг** (`analysis/config.py`) — pydantic-settings, секреты только из `.env`.
- **Trinity-клиент** (`analysis/trinity.py`) — тонкая обёртка над Anthropic SDK,
  нацеленная на Trinity-шлюз; выбор дешёвой/глубокой модели.
- **БД-слой** (`analysis/storage/`) — раздельные async-движки read/analysis,
  read-only маппинг `items`, свои ORM-таблицы, селектор «новых items».
- **Миграции** (`analysis/storage/migrations/`) — своя alembic-история, отдельная
  от движка; создаёт `analysis_runs`, `categories`, `item_analysis` и сидит
  верхний уровень категорий.
- **API** (`analysis/main.py`, `analysis/api/`) — FastAPI-скелет с `GET /health`.

## Стек

Python 3.11+, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, pydantic v2 +
pydantic-settings, Anthropic SDK. Тот же стек, что у движка, — для консистентности.

## Установка

```bash
cd analysis
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # заполнить ANTHROPIC_AUTH_TOKEN и DSN при необходимости
```

## Конфигурация (`.env`)

| Переменная | Назначение | Дефолт |
|------------|-----------|--------|
| `DB_URL_ANALYSIS` | DSN с полными правами на свои таблицы анализа | локальный `findengine` |
| `DB_URL_READ` | read-only DSN к таблицам движка (по умолчанию = analysis) | = `DB_URL_ANALYSIS` |
| `ANTHROPIC_AUTH_TOKEN` | токен Trinity (**не коммитить**) | — |
| `ANTHROPIC_BASE_URL` | базовый URL Trinity | `https://gate.trinity.tg/aurora` |
| `ANALYSIS_MODEL_CHEAP` | дешёвая модель (объём) | `claude-haiku-4-5` |
| `ANALYSIS_MODEL_DEEP` | модель эскалации | `claude-sonnet-4-6` |
| `ANALYSIS_BATCH_SIZE` | размер батча выборки новых items | `50` |

Доступ к данным движка — **read-only**: не писать в `items`/`raw_records`/`jobs`,
не импортировать ORM движка. Своя alembic-история не трогает таблицы движка.

## Миграции

`analysis` ведёт **свою** alembic-историю (та же БД, что у движка, но разные
истории — не пересекаются).

```bash
# применить (нужен поднятый Postgres движка; таблица items должна существовать —
# item_analysis ссылается на items.id внешним ключом)
.venv/bin/python -m alembic upgrade head

# посмотреть план без БД (offline SQL)
.venv/bin/python -m alembic upgrade head --sql

# история
.venv/bin/python -m alembic history
```

Начальная миграция `0001_analysis_initial` создаёт `analysis_runs`,
`categories`, `item_analysis` и сидит верхние категории
(AI, инженерия, продукт, наука, инструменты, прочее).

## Запуск API

```bash
.venv/bin/uvicorn analysis.main:app --reload
# GET http://127.0.0.1:8000/health
```

`GET /health` возвращает `{status, database, trinity_configured}`:
`database` — успешен ли `SELECT 1`, `trinity_configured` — задан ли токен Trinity
(без сетевого вызова). `status` = `ok` при живой БД, иначе `degraded`.

## Тесты / линт / типы

```bash
.venv/bin/python -m pytest -q     # unit-тесты: сеть и Postgres не нужны
.venv/bin/ruff check .
.venv/bin/mypy analysis
```

Тесты гермертичны: Trinity замокан, БД-логика гоняется на in-memory SQLite (типы
ARRAY/JSONB/timestamptz адаптируются через TypeDecorator). Реальный Postgres
нужен только для `alembic upgrade` и боевого запуска.

## Инкрементальная обработка

«Новые items» = те, у которых нет строки в `item_analysis`
(`LEFT JOIN ... WHERE item_analysis IS NULL`) — см. `storage/selector.py`.
Идемпотентно, переживает дозабор. Курсор движка по `id` не ведём: `items.id` —
UUID и не монотонен; для батчинга/наблюдаемости используем `analysis_runs`.

## Структура

```
analysis/
├── pyproject.toml          пакет + dev-зависимости
├── alembic.ini             своя alembic-история
├── .env.example
├── analysis/
│   ├── config.py           настройки из окружения
│   ├── trinity.py          клиент Trinity (Anthropic SDK)
│   ├── main.py             FastAPI: create_app() + app
│   ├── api/
│   │   ├── schemas.py      HealthResponse
│   │   └── routers/health.py
│   └── storage/
│       ├── orm.py          ReadBase (items) + Base (свои таблицы)
│       ├── db.py           read/analysis engine + session
│       ├── selector.py     выборка «новых items»
│       └── migrations/     env.py + versions/0001_analysis_initial.py
└── tests/                  conftest (SQLite) + unit-тесты
```

## Дальше (следующие фазы)

1. Классификация (Haiku → дерево категорий) · 2. Скоринг + тирлист ·
3. `research/` (веб-серч) · 4. Эмбеддинги (pgvector) + analysis API ·
5. UI / панель · 6. Аккаунты, безопасность, аудит.
