# Архитектура find-engine

## 1. Обзор

find-engine — ядро сбора данных из публичных источников (GitHub, Reddit, Hacker
News, arXiv) в единую базу PostgreSQL. Ядро **только собирает и нормализует**
записи: тянет новое инкрементально, приводит к единой модели `Item`,
дедуплицирует по `(source, external_id)` и складывает в таблицы `items` /
`raw_records`, фиксируя ход каждого прогона в `jobs`. Аналитика, поиск
конкурентов, дашборды и семантический поиск — вне scope ядра; они работают
отдельным софтом поверх собранной базы.

## 2. Слоистая архитектура

```
┌──────────────────────────────────────────────────────────────┐
│  API (FastAPI)          find_engine/api/routers/{jobs,health}  │
│   POST /jobs, GET /jobs/{id}, GET /health                      │
└───────────────┬─────────────────────────────┬─────────────────┘
                │ ручной запуск               │ по расписанию
                ▼                             ▼
        ┌───────────────┐           ┌────────────────────────┐
        │  Orchestrator │◄──────────│  Scheduler (APScheduler)│
        │  core/        │           │  core/scheduler.py      │
        │  orchestrator │           └────────────────────────┘
        └───────┬───────┘
                │ create_job → run_job
       ┌────────┴────────┐
       ▼                 ▼
┌──────────────┐   ┌─────────────────────────────────────────┐
│   Sources    │   │              Storage                    │
│  (плагины)   │   │  Repository → ORM → PostgreSQL          │
│  fetch /     │   │  storage/repository.py, storage/db.py   │
│  normalize   │   └─────────────────────────────────────────┘
│  sources/*   │
└──────┬───────┘
       │ Source.normalize (RawRecord → Item)
       ▼
  Normalizer (метод normalize внутри каждого плагина-источника)
```

| Слой | Файлы | Ответственность |
|------|-------|-----------------|
| **API** | `find_engine/api/routers/jobs.py`, `find_engine/api/routers/health.py`, `find_engine/main.py` | HTTP-фасад на FastAPI. Ручной запуск задач (`POST /jobs`), статус и статистика (`GET /jobs/{id}`), живость и список источников (`GET /health`). Регистрирует роутеры в `create_app` (`find_engine/main.py:37`). |
| **Scheduler** | `find_engine/core/scheduler.py` | Cron-планировщик поверх APScheduler. Для каждого источника с непустым cron периодически создаёт и сразу выполняет job (`find_engine/core/scheduler.py:26`). Тонкая обёртка, бизнес-логики не содержит. |
| **Orchestrator** | `find_engine/core/orchestrator.py` | Точка встречи плагина-источника и хранилища. Выполняет прогон одной job: watermark → fetch → normalize → upsert → обновление stats. Управляет транзакциями и переводом job в `failed`. Деталей источников не знает. |
| **Sources** | `find_engine/core/source.py`, `find_engine/sources/__init__.py`, `find_engine/sources/*.py`, `find_engine/sources/http.py` | Плагины-источники по протоколу `Source`. `fetch` тянет сырые `RawRecord`, `normalize` приводит их к `Item`. Реестр (`register` / `get_source` / `available_sources`). Общий HTTP-клиент с retry/backoff. |
| **Normalizer** | метод `Source.normalize` в каждом плагине (`find_engine/core/source.py:31`) | Приведение сырого ответа источника к единой модели `Item`. Не отдельный модуль — часть контракта `Source`, чтобы маппинг жил рядом с источником. |
| **Storage** | `find_engine/storage/repository.py`, `find_engine/storage/db.py`, `find_engine/storage/orm.py` | Доступ к PostgreSQL. `Repository` — тонкая обёртка над сессией: upsert items/raw_records, CRUD jobs, расчёт watermark. `db.py` — async engine и session factory. Транзакциями управляет вызывающий (orchestrator), а не репозиторий (`find_engine/storage/repository.py:21`). |

Модели данных (`find_engine/core/models.py`) — сквозные pydantic-структуры
(`Item`, `RawRecord`, `Job`, `JobState`, `JobStats`), проходящие через все слои.

## 3. Поток данных одного прогона job

Прогон состоит из двух шагов оркестратора: `create_job` (постановка) и
`run_job` (выполнение). Оба определены в `find_engine/core/orchestrator.py`.

**Постановка — `Orchestrator.create_job` (`orchestrator.py:43`):**

1. Открывает сессию, вычисляет watermark: `repo.last_successful_watermark(name)`
   — `finished_at` последнего успешного прогона этого источника.
2. Создаёт job со статусом `queued` и сохранённым `since`, коммитит, возвращает
   `job.id`.

**Выполнение — `Orchestrator.run_job` (`orchestrator.py:52`):**

| Шаг | Действие | Код |
|-----|----------|-----|
| 1. watermark | Загружает job, читает сохранённый `job.since` | `repo.get_job(job_id)` |
| 2. running | Переводит job в `running`, ставит `started_at`, коммитит | `update_job(..., status=running)` |
| 3. fetch | Итерирует `source.fetch(job.since, None)`, `stats.fetched += 1` на каждую запись | `async for raw in source.fetch(...)` |
| 4. normalize | Приводит `RawRecord` к `Item` | `item = source.normalize(raw)` |
| 5. upsert | Пишет `Item` (+ payload в `raw_records`), считает inserted/updated | `repo.upsert_item(item, payload=raw.payload)` |
| 6. success | Переводит job в `success`, пишет `stats` и `finished_at`, коммитит | `update_job(..., status=success, stats=stats)` |

```python
stats = JobStats()
try:
    async for raw in source.fetch(job.since, None):
        stats.fetched += 1
        item = source.normalize(raw)
        _, inserted = await repo.upsert_item(item, payload=raw.payload)
        if inserted:
            stats.inserted += 1
        else:
            stats.updated += 1
    await repo.update_job(job_id, status=JobState.success,
                          stats=stats, finished_at=_now())
    await session.commit()
```

### Транзакционная модель

- **Job — в своей сессии.** Весь прогон идёт в одной сессии/транзакции
  (`async with self._sessionmaker() as session`), поэтому данные (`items` /
  `raw_records`) и финальный статус job фиксируются одним `commit` атомарно.
- **Ошибка → failed в отдельной сессии.** При исключении основная сессия
  откатывается (`session.rollback()`), и статус `failed` (вместе с `error`,
  частичной `stats` и `finished_at`) пишется в **новой** сессии
  `err_session` со своим `commit` (`orchestrator.py:82-93`). Это гарантирует,
  что отметка об ошибке сохранится, даже если откатилась транзакция с данными.
  После записи исключение пробрасывается дальше (`raise`).

## 4. Ключевая абстракция Source

`Source` — это `Protocol` (`find_engine/core/source.py:16`), а не базовый класс.
Источнику достаточно иметь нужную форму, наследоваться ни от чего не нужно.

```python
@runtime_checkable
class Source(Protocol):
    name: str
    def fetch(self, since: datetime | None,
              cursor: str | None) -> AsyncIterator[RawRecord]: ...
    def normalize(self, raw: RawRecord) -> Item: ...
```

Контракт:

| Член | Назначение |
|------|-----------|
| `name` | Уникальный ключ источника в реестре и в полях `source` (`Item` / `Job`). |
| `fetch(since, cursor)` | Async-итератор сырых `RawRecord`. Тянет только новое с момента `since`; `cursor` — для resume/пагинации внутри одного запуска. |
| `normalize(raw)` | Приводит `RawRecord` к единой модели `Item`. |

**Реестр** (там же):

| Функция | Назначение |
|---------|-----------|
| `register(source)` | Регистрирует инстанс по `source.name`; повторная регистрация — `ValueError`. |
| `get_source(name)` | Возвращает источник или `KeyError` со списком известных. |
| `available_sources()` | Отсортированный список зарегистрированных имён. |
| `clear_registry()` | Сброс реестра (только для тестов). |

**Принцип «новый источник = новый плагин».** Чтобы добавить источник, пишут
класс с `name`, `fetch`, `normalize` и регистрируют его в
`register_all` (`find_engine/sources/__init__.py:9`). Orchestrator, Scheduler,
Repository и API работают исключительно через протокол `Source` и модели
`RawRecord` / `Item` — они не содержат `if source == "github"`. Поэтому новый
источник **не требует изменений ядра**: оркестратор «не знает деталей
источников» (`orchestrator.py:3`).

## 5. Инкрементальный сбор и дедупликация

**Per-source watermark.** Перед постановкой job оркестратор берёт точку отсечки
через `Repository.last_successful_watermark(source)` — `finished_at` последнего
прогона со статусом `success` для данного источника
(`find_engine/storage/repository.py:124`):

```sql
SELECT finished_at FROM jobs
WHERE source = :source AND status = 'success'
ORDER BY finished_at DESC LIMIT 1
```

Значение сохраняется в `Job.since` и передаётся в `source.fetch(job.since, None)`,
так что источник тянет только записи новее предыдущего успешного прогона.
Watermark считается отдельно по каждому источнику, поэтому сбои или отставание
одного источника не влияют на отсечку других.

**Дедупликация через upsert.** `Item` уникален по `(source, external_id)`
(`find_engine/core/models.py:20`). `Repository.upsert_item` использует
PostgreSQL `INSERT ... ON CONFLICT (source, external_id) DO UPDATE`
(`find_engine/storage/repository.py:46`) и по `xmax == 0` определяет, была это
вставка или обновление — отсюда `inserted` / `updated` в `JobStats`. Так
повторно увиденная запись не дублируется, а обновляется (например, изменившийся
`score`). Если передан `payload`, в `raw_records` пишется сырой ответ, связанный
с `item_id`.

Итог: watermark сокращает объём `fetch`, а upsert по уникальному ключу страхует
от дублей на границах окон и при пересечении выборок.

## 6. Жизненный цикл приложения

Управляется `lifespan` в `find_engine/main.py:20` (FastAPI `asynccontextmanager`).

**Startup:**

1. `settings = get_settings()` — конфигурация.
2. `register_all(settings)` — инстанцирует и регистрирует все плагины v1
   (`find_engine/sources/__init__.py`).
3. `Orchestrator(get_sessionmaker())` — создаётся и кладётся в
   `app.state.orchestrator`.
4. `Scheduler(orchestrator, settings)` → `scheduler.start()` — поднимает
   cron-задачи для источников с непустым cron; сохраняется в
   `app.state.scheduler`.

**Shutdown** (блок `finally`): `scheduler.shutdown()` — останавливает APScheduler
(`find_engine/core/scheduler.py:48`, `wait=False`).

Порядок важен: источники регистрируются **до** создания Scheduler, иначе
`available_sources()` вернёт пусто и cron-задачи не появятся.

## 7. HTTP-клиент с retry/backoff

Общий клиент `request_with_retry` (`find_engine/sources/http.py:20`) выносит
throttling/повторы из плагинов, чтобы каждый источник не дублировал эту логику.

| Аспект | Поведение |
|--------|-----------|
| Ретраятся статусы | `429, 500, 502, 503, 504` — множество `_RETRY_STATUS` (`http.py:17`). |
| Кол-во попыток | `max_retries` (по умолчанию 3) → до 4 запросов суммарно. |
| Retry-After | При наличии заголок парсится как секунды (`float`) и используется как задержка (`_retry_delay`, `http.py:51`). |
| Экспоненциальный backoff | Если `Retry-After` нет/невалиден — задержка `2.0 ** attempt` (1с, 2с, 4с …). |
| Сетевые ошибки | `httpx.TransportError` / `HTTPStatusError` ретраятся с backoff `2.0 ** attempt`; после исчерпания попыток поднимается последняя ошибка. |
| Успех | На не-ретрайном статусе вызывается `raise_for_status()` и возвращается `Response`. |

Логика цикла (`http.py:30-48`): на ретрайном статусе при незавершённых попытках —
ждём `delay` и повторяем; иначе валидируем и возвращаем ответ. На исключении —
ждём backoff и повторяем, пока не кончатся попытки.
