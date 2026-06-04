# Фаза 0 — каркас модуля `analysis/`

Спека для реализации (swarm из ruflo, TDD). Цель фазы: поднять пустой, но
рабочий и протестированный каркас сервиса анализа. **Без** логики классификации
и скоринга — только фундамент, на который их положат Фазы 1–2.

См. общий план: [`analysis-plan.md`](analysis-plan.md). Trinity: [`Trinity.md`](Trinity.md).

## Definition of Done

- [ ] Пакет `analysis/` ставится (`pip install -e ".[dev]"`), `pytest` зелёный.
- [ ] Trinity-клиент: тонкая обёртка над Anthropic SDK, `base_url` и ключ из env,
      выбор модели по имени, есть unit-тест на конфигурацию (с моком, без сети).
- [ ] Подключение к Postgres: **read-only** доступ к таблицам движка
      (`items`, `raw_records`), отдельный engine/session для своих таблиц.
- [ ] Свои таблицы анализа созданы через Alembic-миграцию.
- [ ] Инкрементальная обработка: курсор по `items`, выборка «только новых».
- [ ] Скелет FastAPI: `GET /health` отвечает (живость + доступность БД и Trinity).
- [ ] `.env.example` с плейсхолдерами (без реальных секретов).
- [ ] README модуля: запуск, миграции, тесты.

## Размещение и стек

- Папка: `analysis/` в корне монорепо, рядом с `search engine/`.
- Стек тот же, что у движка (консистентность): Python 3.11+, FastAPI, SQLAlchemy
  2.0 (async, asyncpg), Alembic, pydantic v2 + pydantic-settings, httpx.
- Модели LLM: **Anthropic SDK** (`anthropic`) поверх Trinity base_url.
- Тесты: pytest + pytest-asyncio, respx/моки — **сеть и реальная БД в unit-тестах
  не нужны** (Trinity мокаем, БД-тесты помечаем как требующие Postgres и
  пропускаем при его отсутствии — как уже сделано в движке для repository-тестов).

## Доступ к данным движка (решение 1а)

Analysis читает **ту же Postgres** напрямую, но к таблицам движка относится как к
read-only внешнему контракту:

- НЕ импортировать ORM движка и НЕ писать в `items`/`raw_records`/`jobs`.
- Свой минимальный read-маппинг таблицы `items` (только нужные колонки):
  `id, source, external_id, title, url, author, body, score, tags, created_at, fetched_at`.
- Желательно отдельная **роль БД** с правами только `SELECT` на таблицы движка и
  полными правами на схему/таблицы анализа (детали хардненинга — Фаза 6, но
  заложить раздельные DSN можно сразу: `DB_URL_READ` / `DB_URL_ANALYSIS`, по
  умолчанию совпадают).

## Схема таблиц анализа (черновик — финализировать в начале фазы)

Свои таблицы, ссылаются на `items.id`. Под результаты следующих фаз заводим
структуру заранее, но без данных.

- **`analysis_runs`** — прогон анализа (аналог `jobs` у движка): `id`, `kind`
  (`classify`/`score`/…), `status`, `cursor`, `stats` (JSONB), `error`,
  `started_at`, `finished_at`. Нужно для инкрементальности и наблюдаемости.
- **`categories`** — узел дерева категорий: `id`, `parent_id` (nullable, self-FK),
  `slug`, `title`, `approved` (bool — для гибридной таксономии), `created_at`.
  В Фазе 0 — только таблица + сидинг верхнего уровня (AI, инженерка, продукт,
  наука…); раскладка по ней — Фаза 1.
- **`item_analysis`** — результат анализа одного item (1:1 к `items.id`):
  `item_id` (FK→items.id, unique), `category_id` (nullable, Фаза 1),
  `scores` (JSONB: актуальность/сложность/…, Фаза 2), `coefficient` (float,
  Фаза 2), `tier` (char, Фаза 2), `embedding` (vector, Фаза 4 — колонку пока не
  создаём или оставляем nullable-задел), `analyzed_at`, `model_used`.

> Миграции анализа держим в **своей** alembic-истории (отдельный
> `version_locations`), чтобы не пересекаться с миграциями движка в той же БД.
> Уточнить в начале фазы: одна общая alembic-конфигурация на монорепо или
> раздельные. Рекомендация — раздельные (движок не должен знать про анализ).

## Инкрементальная обработка

- Watermark по `items`. Нюанс: `items.id` — UUID (`gen_random_uuid()`), **не
  монотонный**, поэтому курсор вести по `fetched_at` (timestamptz) +
  тай-брейк по `id`, либо хранить множество уже обработанных `item_id` через
  `item_analysis` (LEFT JOIN … WHERE item_analysis IS NULL).
- Рекомендация: «новые items» = те, у которых нет строки в `item_analysis`.
  Просто, идемпотентно, переживает дозабор. Курсор в `analysis_runs` — для
  наблюдаемости и батчинга.

## Trinity-клиент

- Env: `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora`.
- Обёртка: `complete(messages, model, ...)` с дефолт-моделью из конфига
  (`ANALYSIS_MODEL_CHEAP=claude-haiku-4-5`), возможностью эскалации
  (`ANALYSIS_MODEL_DEEP=claude-sonnet-4-6` / `claude-opus-4-8`).
- Секреты — только из env (паттерн движка: `config.py` на pydantic-settings).
- Unit-тест: клиент конструируется с нужным base_url/моделью; вызов замокан.

## `.env.example` (плейсхолдеры)

```
# Database (общая с движком)
DB_URL_ANALYSIS=postgresql+asyncpg://analysis:analysis@localhost:5432/findengine
DB_URL_READ=postgresql+asyncpg://analysis_ro:analysis_ro@localhost:5432/findengine

# Trinity (Anthropic-совместимый шлюз)
ANTHROPIC_AUTH_TOKEN=
ANTHROPIC_BASE_URL=https://gate.trinity.tg/aurora
ANALYSIS_MODEL_CHEAP=claude-haiku-4-5
ANALYSIS_MODEL_DEEP=claude-sonnet-4-6

# Обработка
ANALYSIS_BATCH_SIZE=50
```

## Чего НЕ делаем в Фазе 0 (YAGNI)

- Промптов классификации/скоринга и вызовов модели на реальных данных — Фазы 1–2.
- pgvector/эмбеддингов — Фаза 4 (колонку-задел не активируем).
- Веб-серча — Фаза 3. UI — Фаза 5. Аккаунтов/безопасности — Фаза 6.

## Порядок реализации (TDD)

1. Каркас пакета: `pyproject.toml`, `config.py`, структура `analysis/`.
2. Trinity-клиент + unit-тест (мок).
3. БД-слой: read-маппинг `items`, ORM своих таблиц, async engine/session.
4. Alembic своей истории + миграция (`analysis_runs`, `categories`,
   `item_analysis`) + сидинг верхних категорий.
5. Селектор «новых items» (LEFT JOIN на `item_analysis`) + тест на моке БД.
6. FastAPI-скелет: `GET /health` (БД + Trinity reachable), приложение поднимается.
7. README модуля, прогон `pytest`/`ruff`/`mypy`.

## Верификация

- `pytest` зелёный (Trinity мокнут, БД-тесты skip без Postgres).
- Локально с Postgres движка: `alembic upgrade head` (история анализа) создаёт
  таблицы; `GET /health` → ok; селектор «новых» возвращает все существующие
  items (т.к. `item_analysis` пуст).
- `ruff` и `mypy` чистые (как в движке).
