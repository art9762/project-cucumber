# Эксплуатация find-engine

Практическое руководство по установке, запуску и сопровождению ядра
**find-engine** — сервиса парсинга публичных источников (GitHub, Reddit,
Hacker News, arXiv) в единую базу PostgreSQL.

Ядро **только собирает и нормализует** данные. Поиск, аналитика и сравнение
конкурентов реализуются отдельным софтом поверх собранной базы.

Связанные документы:

- [`docs/api.md`](api.md) — детали HTTP API (тело запросов/ответов).
- [`docs/architecture.md`](architecture.md) — устройство компонентов.
- [`docs/data-model.md`](data-model.md) — схема таблиц.

---

## 1. Требования

| Компонент | Версия / примечание |
|-----------|---------------------|
| Python | `>=3.11` (см. `requires-python` в `pyproject.toml`) |
| Docker + Docker Compose | для локального PostgreSQL (можно и внешний Postgres) |
| PostgreSQL | 16 (образ `postgres:16` в `docker-compose.yml`); нужна функция `gen_random_uuid()` из расширения `pgcrypto` |

Ключевые runtime-зависимости (из `pyproject.toml`):

- **fastapi** `>=0.110` — HTTP API.
- **uvicorn[standard]** `>=0.29` — ASGI-сервер.
- **sqlalchemy** `>=2.0` (async) + **greenlet** `>=3.0` — ORM и асинхронные сессии.
- **asyncpg** `>=0.29` — асинхронный драйвер PostgreSQL.
- **alembic** `>=1.13` — миграции схемы.
- **apscheduler** `>=3.10` — cron-планировщик сбора.
- **httpx** `>=0.27` — HTTP-клиент к источникам.
- **feedparser** `>=6.0` — парсинг RSS/Atom (arXiv).
- **pydantic** `>=2.6` / **pydantic-settings** `>=2.2` — модели и конфиг из окружения.

Dev-зависимости (extra `[dev]`): **pytest** `>=8.0`, **pytest-asyncio** `>=0.23`,
**respx** `>=0.21` (моки HTTP), **ruff** `>=0.4` (линт), **mypy** `>=1.9` (типы).

---

## 2. Установка

Из корня репозитория:

```bash
# 1. Виртуальное окружение
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Установка пакета вместе с dev-зависимостями (editable)
pip install -e ".[dev]"

# 3. Конфигурация из шаблона
cp .env.example .env
```

Откройте `.env` и заполните значения (как минимум проверьте `DB_URL`):

- `DB_URL` — строка подключения SQLAlchemy/asyncpg. По умолчанию указывает на
  локальный контейнер: `postgresql+asyncpg://findengine:findengine@localhost:5432/findengine`.
- `GITHUB_TOKEN` — опционально, но рекомендуется (иначе низкие анонимные лимиты GitHub API).
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` — опционально для Reddit.
- `HTTP_TIMEOUT`, `HTTP_MAX_RETRIES` — поведение HTTP-клиента.
- `GITHUB_TOPICS`, `REDDIT_SUBREDDITS`, `ARXIV_CATEGORIES`, `HN_QUERY`, `HN_MIN_POINTS` —
  что именно собирать по каждому источнику (через запятую, где это список).
- `CRON_*` — расписание планировщика (см. раздел 6).

Конфигурация читается через `pydantic-settings` (`find_engine/config.py`):
файл `.env` подхватывается автоматически, а любые одноимённые переменные
окружения переопределяют значения из файла. `.env` в `.gitignore` —
не коммитьте секреты.

---

## 3. Запуск PostgreSQL через docker-compose

```bash
docker-compose up -d
```

Параметры из `docker-compose.yml`:

- образ `postgres:16`;
- порт **5432** проброшен на хост;
- пользователь / пароль / база: **findengine / findengine / findengine**;
- данные сохраняются в именованном томе `pgdata` (переживают пересоздание контейнера);
- настроен `healthcheck` через `pg_isready -U findengine` (интервал 5s, 5 ретраев).

Проверка готовности:

```bash
# статус и healthcheck контейнера
docker-compose ps

# дождаться, пока healthcheck станет healthy
docker inspect --format '{{.State.Health.Status}}' "$(docker-compose ps -q postgres)"

# прямой пинг базы
docker-compose exec postgres pg_isready -U findengine
```

Остановка / полный сброс данных:

```bash
docker-compose down          # остановить, том pgdata сохраняется
docker-compose down -v       # ВНИМАНИЕ: удалит том pgdata вместе с данными
```

---

## 4. Миграции (Alembic)

Применить схему к базе:

```bash
alembic upgrade head
```

Начальная миграция `0001_initial` создаёт:

- расширение `pgcrypto` (даёт `gen_random_uuid()` для первичных ключей);
- **`items`** — нормализованные записи для поиска; уникальность по
  `(source, external_id)` (дедуп), индексы по `source` и `created_at`;
- **`raw_records`** — сырые ответы источников (`payload` JSONB), FK на `items`
  с `ON DELETE CASCADE`;
- **`jobs`** — задачи сбора: `status`, `since` (per-source watermark), `cursor`,
  `stats` (JSONB), `error`, тайминги; индекс по `(source, status)`.

Откат на одну ревизию назад:

```bash
alembic downgrade -1
```

Как устроен `find_engine/storage/migrations/env.py`:

- работает в **async**-режиме (`create_async_engine`);
- URL базы берётся не из `alembic.ini`, а из настроек приложения —
  `get_settings().db_url` (т.е. из `DB_URL` в `.env`/окружении);
- `target_metadata = Base.metadata` (ORM из `find_engine/storage/orm.py`),
  поэтому автогенерация миграций видит модели.

Создать новую миграцию после изменения ORM-моделей:

```bash
# автогенерация diff'а схемы (требует поднятого Postgres)
alembic revision --autogenerate -m "описание изменения"

# или пустой шаблон под ручную миграцию
alembic revision -m "описание изменения"
```

Новый файл появится в `find_engine/storage/migrations/versions/`. Проверьте
сгенерированный код перед применением, затем `alembic upgrade head`.

---

## 5. Запуск API

```bash
# Dev: автоперезагрузка при изменении кода
uvicorn find_engine.main:app --reload

# Prod: явные host/port, без reload
uvicorn find_engine.main:app --host 0.0.0.0 --port 8000
```

Порт по умолчанию у uvicorn — **8000**. Приложение (`find_engine/main.py`)
в `lifespan` при старте:

1. регистрирует все источники (`register_all`);
2. поднимает `Orchestrator` поверх async-sessionmaker;
3. запускает `Scheduler` (cron-планировщик) — см. раздел 6;
4. при остановке корректно гасит планировщик (`scheduler.shutdown()`).

Документация эндпоинтов доступна на работающем сервере: Swagger UI на
`/docs`, OpenAPI-схема на `/openapi.json`.

---

## 6. Запуск сбора

### Вручную (через API)

Поставить задачу сбора по конкретному источнику:

```bash
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"source":"arxiv"}'
```

Ответ — `202 Accepted` с телом задачи (включая `id`); сам сбор выполняется
в фоне (`asyncio.create_task`). Доступные источники: `github`, `reddit`,
`hackernews`, `arxiv`. Неизвестный `source` → `400` со списком доступных.
Подробности тел запросов/ответов — в [`docs/api.md`](api.md).

### По расписанию (cron-планировщик)

Расписание задаётся переменными `CRON_*` в `.env`, по одной на источник
(стандартный 5-польный cron):

```bash
CRON_ARXIV=0 */6 * * *
CRON_HACKERNEWS=0 */3 * * *
CRON_GITHUB=0 */6 * * *
CRON_REDDIT=0 */6 * * *
```

Как это работает (`find_engine/core/scheduler.py`, `Scheduler.start`):

- для каждого зарегистрированного источника берётся `settings.cron_for(name)`;
- **пустая строка cron → источник пропускается** (расписание выключено);
- иначе задача регистрируется в `AsyncIOScheduler` через
  `CronTrigger.from_crontab(cron, timezone="UTC")` с `id=cron-<source>`,
  `replace_existing=True` и **`max_instances=1`** (одновременно не запустится
  второй прогон того же источника);
- все триггеры считаются в **UTC** (планировщик создан с `timezone="UTC"`);
- при срабатывании планировщик создаёт job (`create_job`) и сразу её выполняет
  (`run_job`) — тот же путь, что и при ручном `POST /jobs`.

Сбор инкрементальный: `create_job` вычисляет watermark (`since`) из последнего
**успешного** запуска по этому источнику, поэтому повторные прогоны не дублируют
уже собранные записи (дедуп по `(source, external_id)`).

По умолчанию в `find_engine/config.py` все `cron_*` пустые — расписание
включается только тем, что вы пропишете в `.env`/окружении.

---

## 7. Тесты, линтинг, типы

```bash
pytest                       # весь набор
pytest tests/test_repository.py   # только репозиторные (нужен Postgres)
```

Как устроены тесты:

- `asyncio_mode = "auto"` (в `pyproject.toml`) — async-тесты не требуют
  отдельных маркеров.
- **Тесты нормализации** (`test_normalize_*.py`) — без БД, работают на
  JSON-фикстурах из `tests/fixtures`.
- **Orchestrator-тест** (`test_orchestrator.py`) — без Postgres: использует
  мок-источник и in-memory `FakeRepo` + фейковую сессию.
- **Repository-тесты** (`test_repository.py`) — **требуют реального
  PostgreSQL** (проверяют `ON CONFLICT`/upsert и `xmax`-дедуп). Фикстура
  пытается подключиться к `DB_URL`; если база недоступна — модуль
  **пропускается** (`pytest.skip`), а не падает. Чтобы они отработали,
  предварительно поднимите базу:

  ```bash
  docker-compose up -d
  pytest tests/test_repository.py
  ```

Качество кода:

```bash
ruff check .                 # линт (line-length 100, target py311)
mypy find_engine             # проверка типов (python 3.11)
```

---

## 8. Эксплуатация

**Где смотреть статус**

- Живость сервиса и список зарегистрированных источников:

  ```bash
  curl http://localhost:8000/health
  # {"status":"ok","sources":["github","reddit","hackernews","arxiv"]}
  ```

- Статус конкретной задачи (текущее состояние + `stats`):

  ```bash
  curl http://localhost:8000/jobs/<JOB_ID>
  ```

  Поле `status` принимает значения `queued` → `running` → `success` / `failed`
  (enum `JobState`). В `stats` — счётчики `fetched` / `inserted` / `updated` / `skipped`.

**Логирование**

`find_engine/main.py` инициализирует `logging.basicConfig(level=logging.INFO)`.
В stdout/stderr пишутся события планировщика («Scheduled …», «Scheduler
triggered … → job …») и ошибки прогонов. uvicorn пишет access-логи туда же.
Для prod направляйте stdout/stderr в свой сборщик логов
(systemd journal, Docker logs, и т. п.).

**Поведение при ошибке job**

Если во время прогона источник падает (см. `Orchestrator.run_job`):

- транзакция откатывается, статус job переводится в **`failed`**, текст
  исключения сохраняется в поле `error` записи job, проставляется `finished_at`;
- частичная статистика (`stats`), накопленная до сбоя, сохраняется;
- ошибка логируется (`logger.exception`).

При запуске через `POST /jobs` исключение фонового прогона уже зафиксировано
в самой job и наружу не пробрасывается — диагностируйте через
`GET /jobs/{id}` (поля `status` и `error`).

---

## 9. Production-замечания

- **Конфигурация через переменные окружения, а не `.env`.** В проде задавайте
  `DB_URL`, токены и `CRON_*` напрямую как переменные окружения (в
  systemd-unit, Docker `--env`/`env_file`, Kubernetes Secret/ConfigMap).
  Файл `.env` удобен локально, но не должен попадать в образ/репозиторий.

- **Один процесс из-за встроенного планировщика.** `Scheduler` поднимается в
  `lifespan` приложения, т.е. **внутри каждого worker-процесса**. Если
  запустить uvicorn/gunicorn с несколькими воркерами (`--workers N` /
  `-w N`), cron-задачи **продублируются** — каждый воркер заведёт свой
  планировщик. Для одиночного хоста запускайте API **одним процессом**
  (`--workers 1`). Если нужно горизонтальное масштабирование API, выносите
  планировщик в отдельный одиночный экземпляр (например, отдельный деплой с
  включённым `CRON_*`, а у API-реплик — пустыми), чтобы расписание работало
  ровно в одном месте.

- **Бэкапы PostgreSQL.** Данные — единственная ценность ядра. Настройте
  регулярные дампы и проверяйте восстановление:

  ```bash
  # дамп из контейнера compose
  docker-compose exec -T postgres pg_dump -U findengine findengine > backup.sql

  # восстановление
  cat backup.sql | docker-compose exec -T postgres psql -U findengine findengine
  ```

  Том `pgdata` переживает пересоздание контейнера, но `docker-compose down -v`
  его удалит — храните дампы вне хоста с БД.
