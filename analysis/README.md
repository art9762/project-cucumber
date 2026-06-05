# analysis — модуль анализа идей

Сервис анализа поверх движка сбора (`../search engine/`). Движок собирает идеи из
публичных источников в Postgres (`items`, `raw_records`, `jobs`); `analysis`
читает эти данные **read-only** и складывает результаты анализа в свои таблицы.

Реализованы **Фазы 0–6**: каркас, классификация, скоринг/тирлист, веб-ресёрч,
эмбеддинги/семантический поиск и аутентификация. Общий план:
[`../docs/analysis-plan.md`](../docs/analysis-plan.md); спеки фаз — в
[`../docs/`](../docs/) (`phase-0-…` … `phase-6-…`).

## Карта модулей

| Пакет | Назначение | Фаза |
|-------|-----------|------|
| `analysis/config.py` | настройки из окружения (pydantic-settings), секреты только из `.env` | 0 |
| `analysis/trinity.py` | клиент Trinity (Anthropic SDK на `base_url` шлюза), выбор дешёвой/глубокой модели | 0 |
| `analysis/storage/` | раздельные async-движки read/analysis, ORM (read-only `items` + свои таблицы), селектор «новых items», alembic-история | 0 |
| `analysis/classify/` | классификация items по дереву категорий (Haiku), предложение новых веток | 1 |
| `analysis/score/` | скоринг → коэффициент + тир S/A/B/C/D, config-driven формула, эскалация на глубокую модель | 2 |
| `analysis/research/` | веб-ресёрч и поиск конкурентов через серверный `web_search` Trinity | 3 |
| `analysis/embed/` | локальные эмбеддинги (fastembed, CPU) + семантический поиск / конкуренты по pgvector | 4 |
| `analysis/auth/` | серверные сессии (HttpOnly-cookie, НЕ JWT), argon2, роли admin/viewer, CLI сидинга | 6 |
| `analysis/api/` | FastAPI-роутеры и pydantic-схемы всех эндпоинтов | 0–6 |
| `analysis/main.py` | `create_app()` + `app`: регистрация роутеров и CORS | 0/5 |

## Стек

Python 3.11+, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, pydantic v2 +
pydantic-settings, Anthropic SDK (через Trinity), `fastembed` + `pgvector`
(эмбеддинги), `argon2-cffi` (хеширование паролей).

## Установка

```bash
cd analysis
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env   # заполнить ANTHROPIC_AUTH_TOKEN и DSN при необходимости
```

## HTTP API

Базовый URL локально — `http://127.0.0.1:8113` (порт задаётся флагом uvicorn; в
проде тот же порт за nginx, см. [`../docs/phase-6-deploy-hardening.md`](../docs/phase-6-deploy-hardening.md)).

Колонка **Auth** отражает реальный `Depends(...)` роутера:
`—` — без аутентификации; `viewer+` — нужна сессия любой роли
(`get_current_user`); `admin` — нужна роль admin (`require_role("admin")`).

| Метод | Путь | Параметры | Ответ | Auth |
|-------|------|-----------|-------|------|
| GET | `/health` | — | `HealthResponse` `{status, database, trinity_configured}` | — |
| POST | `/auth/login` | body `{username, password}` | `UserOut` `{username, role}` + выставляет cookie | — |
| POST | `/auth/logout` | — | `204`, чистит cookie | — |
| GET | `/auth/me` | — | `UserOut` `{username, role}` | viewer+ |
| GET | `/categories` | — | `CategoryTreeNode[]` (вложенное дерево) | viewer+ |
| GET | `/categories/pending` | — | `CategoryOut[]` (очередь модерации) | viewer+ |
| POST | `/categories/{id}/approve` | path `id: UUID` | `ApproveResponse` `{ok, id, approved}` | admin |
| POST | `/categories/{id}/reject` | path `id: UUID` | `RejectResponse` `{ok, id}` (удаляет категорию) | admin |
| POST | `/classify` | query `limit?` | `ClassifyRunOut` `{seen, classified, suggested, failed, errors}` | admin |
| GET | `/tierlist` | query `tier?`, `category_id?: UUID`, `limit?` | `TierItemOut[]` (сорт. по coefficient ↓) | viewer+ |
| GET | `/items/{item_id}/score` | path `item_id: UUID` | `ItemScoreOut` (+`model_used`) | viewer+ |
| POST | `/score` | query `limit?` | `ScoreRunOut` `{seen, scored, escalated, failed, tier_counts, errors}` | admin |
| GET | `/research` | query `has_competitors?`, `limit?` | `ItemResearchOut[]` | viewer+ |
| GET | `/items/{item_id}/research` | path `item_id: UUID` | `ItemResearchOut` | viewer+ |
| POST | `/research` | query `limit?`, `min_tier?`, `min_coefficient?` (0..1) | `ResearchRunOut` `{seen, researched, competitors_found, failed, errors}` | admin |
| POST | `/search` | body `{query, limit=10}` | `SearchHitOut[]` (семантический поиск) | viewer+ |
| GET | `/items/{item_id}/competitors` | path `item_id: UUID`, query `limit=10` | `SearchHitOut[]` (похожие по вектору) | viewer+ |
| POST | `/embed` | query `limit?` | `EmbedRunOut` `{seen, embedded, failed, model, dim, errors}` | admin |

Замечания по контракту:
- `/items/{id}/competitors` возвращает `SearchHitOut[]` (соседи по вектору), а не
  `CompetitorOut`. `CompetitorOut` встречается только вложенным в
  `ItemResearchOut.competitors` (конкуренты, найденные веб-ресёрчем).
- Все три auth-эндпоинта (`/auth/login`, `/auth/logout`, `/auth/me`) сами по себе
  **без** `Depends` на роль; `/auth/me` внутри требует валидную сессию и отдаёт
  401, если её нет. `/health` тоже публичный (всегда `200`, состояние — в теле).
- Cookie сессии — `cucumber_session` (имя из конфига), HttpOnly, SameSite=Lax,
  Secure — по `SESSION_COOKIE_SECURE`.

Схемы ответов определены в `analysis/api/*_schemas.py`.

## Конфигурация (`.env`)

Все настройки — в `analysis/config.py` (pydantic-settings, env_file=`.env`).
Имена env-переменных = имена полей в верхнем регистре. Секреты (помечены 🔒)
берутся **только** из окружения и не коммитятся.

| Переменная | Назначение | Дефолт |
|------------|-----------|--------|
| `DB_URL_ANALYSIS` | DSN с полными правами на свои таблицы анализа | `postgresql+asyncpg://analysis:analysis@localhost:5432/findengine` |
| `DB_URL_READ` | read-only DSN к таблицам движка (фолбэк на analysis, если пуст) | = `DB_URL_ANALYSIS` |
| `ANTHROPIC_AUTH_TOKEN` 🔒 | токен Trinity | `None` |
| `ANTHROPIC_BASE_URL` | базовый URL Trinity | `https://gate.trinity.tg/aurora` |
| `ANALYSIS_MODEL_CHEAP` | дешёвая модель (объём: классификация/скоринг) | `claude-haiku-4-5` |
| `ANALYSIS_MODEL_DEEP` | модель эскалации скоринга | `claude-sonnet-4-6` |
| `ANALYSIS_BATCH_SIZE` | размер батча выборки новых items | `50` |
| `SCORING_WEIGHTS` | переопределение весов формулы (JSON-строка) | `None` → `ScoringConfig.default()` |
| `SCORING_BIAS` | смещение формулы | `None` |
| `SCORING_TIERS` | пороги тиров (JSON-строка `[["S",0.80],…]`) | `None` |
| `ESCALATE_MIN_CONFIDENCE` | порог уверенности для эскалации | `None` |
| `ESCALATE_HIGH_COEFFICIENT` | высокий коэффициент → эскалация | `None` |
| `ESCALATE_BOUNDARY_MARGIN` | близость к границе тира → эскалация | `None` |
| `RESEARCH_MODEL` | модель веб-ресёрча (по умолчанию глубокая) | `claude-sonnet-4-6` |
| `RESEARCH_MAX_SEARCHES` | максимум веб-поисков на item | `3` |
| `EMBEDDING_MODEL` | локальная модель fastembed | `BAAI/bge-small-en-v1.5` |
| `EMBEDDING_DIM` | размерность вектора (= `EMBEDDING_DIM` в `storage/orm.py`) | `384` |
| `SESSION_SECRET` 🔒 | секрет сессий (резерв; сам токен опаковый в БД) | `dev-insecure-change-me` |
| `SESSION_TTL_HOURS` | срок жизни сессии | `24` |
| `SESSION_COOKIE_NAME` | имя session-cookie | `cucumber_session` |
| `SESSION_COOKIE_SECURE` | флаг Secure на cookie (в проде `true`) | `false` |
| `CORS_ORIGINS` | CSV-список origin'ов UI для credentialed-CORS (пусто → CORS выключен) | `""` |

`SCORING_WEIGHTS`/`SCORING_TIERS` принимаются как JSON-строки, напр.
`SCORING_WEIGHTS='{"relevance":0.45,"complexity":-0.10}'`. Wildcard `*` в
`CORS_ORIGINS` несовместим с cookie-сессиями (`allow_credentials=True`) — только
явный список; CORS-middleware подключается, лишь если список непуст.

Доступ к данным движка — **read-only**: не писать в `items`/`raw_records`/`jobs`,
не импортировать ORM движка. Своя alembic-история не трогает таблицы движка.

## CLI

Прогоны можно запускать без API (тот же код, что за POST-эндпоинтами). Вывод —
JSON со статистикой прогона.

```bash
# Классификация новых items (Фаза 1)
.venv/bin/python -m analysis.classify [--limit N] [--model NAME]

# Скоринг (Фаза 2)
.venv/bin/python -m analysis.score [--limit N] [--cheap-model NAME] [--deep-model NAME]

# Веб-ресёрч (Фаза 3)
.venv/bin/python -m analysis.research [--limit N] [--min-tier S] \
    [--min-coefficient 0.0..1.0] [--model NAME] [--max-searches N]

# Эмбеддинги (Фаза 4)
.venv/bin/python -m analysis.embed [--limit N] [--model NAME]

# Сидинг учёток (Фаза 6) — пишет в таблицу users
.venv/bin/python -m analysis.auth create-admin --username X --password Y
.venv/bin/python -m analysis.auth create-user  --username X --password Y [--role admin|viewer]
```

`create-admin`/`create-user` хешируют пароль argon2 и падают с ошибкой, если
username уже существует. Роль по умолчанию у `create-user` — `viewer`.

## Миграции

`analysis` ведёт **свою** alembic-историю (та же БД, что у движка, но истории не
пересекаются). Нужен поднятый Postgres движка (таблица `items` должна
существовать — внешние ключи ссылаются на `items.id`).

```bash
.venv/bin/python -m alembic upgrade head          # применить
.venv/bin/python -m alembic upgrade head --sql    # offline-план без БД
.venv/bin/python -m alembic history
```

| Ревизия | Создаёт |
|---------|---------|
| `0001_analysis_initial` | `analysis_runs`, `categories` (+seed верхних категорий), `item_analysis`; расширение `pgcrypto` |
| `0002_research_embeddings` | `item_research`, `item_embeddings` (pgvector `vector(384)`); расширение `vector` |
| `0003_auth` | `users`, `sessions` (серверные сессии, индексы по `username`/`token`) |

Seed верхних категорий: AI, инженерия, продукт, наука, инструменты, прочее.

## Запуск API

```bash
SESSION_SECRET='change-me' \
CORS_ORIGINS='http://localhost:5173,http://127.0.0.1:5173' \
.venv/bin/uvicorn analysis.main:app --port 8113 --reload
# GET http://127.0.0.1:8113/health
```

`GET /health` возвращает `{status, database, trinity_configured}`: `database` —
успешен ли `SELECT 1`, `trinity_configured` — задан ли токен Trinity (без
сетевого вызова). `status` = `ok` при живой БД, иначе `degraded`.

## Тесты / линт / типы

В пути репозитория есть пробел (`Project cucumber`) — вызывайте инструменты по
**абсолютным** путям внутри `analysis/`, либо предварительно `cd analysis`.

```bash
.venv/bin/python -m pytest -q     # unit-тесты: сеть и Postgres не нужны
.venv/bin/ruff check .
.venv/bin/mypy analysis
```

Тесты герметичны: Trinity замокан, БД-логика гоняется на in-memory SQLite (типы
ARRAY/JSONB/timestamptz/pgvector адаптируются через TypeDecorator), эмбеддинги в
тестах считаются без загрузки fastembed. Реальный Postgres (pgvector) нужен
только для `alembic upgrade` и боевого запуска.

## Инкрементальная обработка

«Новые items» = те, у которых нет соответствующей строки результата
(`LEFT JOIN ... WHERE ... IS NULL`) — см. `storage/selector.py` и
`<module>/selector.py`. Идемпотентно, переживает дозабор. Курсор движка по `id`
не ведём: `items.id` — UUID и не монотонен; для батчинга/наблюдаемости
используем `analysis_runs` (kind = `classify`/`score`/`research`/`embed`).
