# find-engine — HTTP API

Справочник по HTTP API ядра парсинга публичных источников. API построен на FastAPI
(заголовок приложения `find-engine`, версия `0.1.0`).

## Запуск

```bash
uvicorn find_engine.main:app --host 0.0.0.0 --port 8000
```

Интерактивная документация Swagger UI доступна на `/docs`, схема OpenAPI — на `/openapi.json`.

При старте приложения регистрируются источники, поднимается orchestrator и
фоновый scheduler (см. `find_engine/main.py`).

База для примеров: `http://localhost:8000`.

---

## GET /health

Проверка живости сервиса и получение списка зарегистрированных источников.

**Ответ `200 OK`** (`HealthResponse`):

| Поле      | Тип         | Описание                                   |
|-----------|-------------|--------------------------------------------|
| `status`  | `string`    | Признак живости, всегда `"ok"`.            |
| `sources` | `string[]`  | Список доступных источников для `POST /jobs`. |

**Пример**

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "sources": ["github", "reddit", "hackernews", "arxiv"]
}
```

---

## POST /jobs

Запуск сбора по выбранному источнику. Job создаётся синхронно, а сам сбор
запускается в фоне через `asyncio.create_task` — ответ возвращается сразу, не
дожидаясь завершения работы.

**Тело запроса** (`CreateJobRequest`):

| Поле     | Тип      | Обяз. | Описание                                          |
|----------|----------|-------|---------------------------------------------------|
| `source` | `string` | да    | Имя источника из `GET /health` (`github`, `reddit`, `hackernews`, `arxiv`). |

**Ответ `202 Accepted`** — тело `JobResponse` (см. ниже). На момент ответа job,
как правило, ещё в состоянии `queued`/`running`.

**Ошибка `400 Bad Request`** — неизвестный источник. В `detail` перечислены
доступные источники.

**Пример запроса**

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "github"}'
```

```json
{
  "source": "github"
}
```

**Пример ответа `202`**

```json
{
  "id": "3f9c1b8a-5e2d-4a6f-9c7b-1e2d3f4a5b6c",
  "source": "github",
  "status": "queued",
  "since": null,
  "cursor": null,
  "stats": {
    "fetched": 0,
    "inserted": 0,
    "updated": 0,
    "skipped": 0
  },
  "error": null,
  "started_at": null,
  "finished_at": null
}
```

**Пример ошибки `400`**

```json
{
  "detail": "Unknown source 'twitter'. Available: ['github', 'reddit', 'hackernews', 'arxiv']"
}
```

---

## GET /jobs/{job_id}

Получить текущий статус job по его `id` (UUID).

**Path-параметр**

| Параметр  | Тип    | Описание           |
|-----------|--------|--------------------|
| `job_id`  | `UUID` | Идентификатор job. |

**Ответ `200 OK`** (`JobResponse`):

| Поле             | Тип                  | Описание                                                        |
|------------------|----------------------|----------------------------------------------------------------|
| `id`             | `UUID`               | Идентификатор job.                                             |
| `source`         | `string`             | Источник сбора.                                               |
| `status`         | `string`             | Состояние job: `queued`, `running`, `success`, `failed`.      |
| `since`          | `datetime \| null`   | Watermark источника — нижняя граница выборки по времени.       |
| `cursor`         | `string \| null`     | Курсор для возобновления (resume) постраничного сбора.         |
| `stats`          | `object`             | Счётчики выполнения (см. ниже).                                |
| `stats.fetched`  | `int`                | Сколько записей получено от источника.                         |
| `stats.inserted` | `int`                | Сколько новых записей вставлено.                               |
| `stats.updated`  | `int`                | Сколько существующих записей обновлено.                        |
| `stats.skipped`  | `int`                | Сколько записей пропущено (дубликаты/без изменений).           |
| `error`          | `string \| null`     | Текст ошибки, если `status = failed`.                          |
| `started_at`     | `datetime \| null`   | Время начала выполнения.                                       |
| `finished_at`    | `datetime \| null`   | Время завершения.                                              |

**Ошибка `404 Not Found`** — job с таким `id` не существует.

**Пример**

```bash
curl http://localhost:8000/jobs/3f9c1b8a-5e2d-4a6f-9c7b-1e2d3f4a5b6c
```

```json
{
  "id": "3f9c1b8a-5e2d-4a6f-9c7b-1e2d3f4a5b6c",
  "source": "github",
  "status": "success",
  "since": "2026-06-01T00:00:00Z",
  "cursor": "page=4",
  "stats": {
    "fetched": 120,
    "inserted": 95,
    "updated": 18,
    "skipped": 7
  },
  "error": null,
  "started_at": "2026-06-04T10:15:02Z",
  "finished_at": "2026-06-04T10:15:41Z"
}
```

**Пример ошибки `404`**

```json
{
  "detail": "Job not found"
}
```

---

## Состояния job

Поле `status` принимает одно из значений перечисления `JobState`:

| Состояние   | Описание                                                              |
|-------------|----------------------------------------------------------------------|
| `queued`    | Job создан, ожидает запуска. Начальное состояние после `POST /jobs`. |
| `running`   | Сбор выполняется в фоне.                                              |
| `success`   | Сбор завершён успешно. Итоги — в `stats`, время — в `finished_at`.    |
| `failed`    | Сбор завершился ошибкой. Причина — в поле `error`.                    |

---

## Типичный сценарий

1. Узнать доступные источники через `GET /health`.
2. Запустить сбор через `POST /jobs` — получить `id` и код `202`.
3. Опрашивать (polling) `GET /jobs/{id}`, пока `status` не станет `success` или `failed`.

```bash
# 1. Доступные источники
curl http://localhost:8000/health

# 2. Запуск сбора, сохраняем id
JOB_ID=$(curl -s -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{"source": "hackernews"}' | jq -r .id)

echo "Job: $JOB_ID"

# 3. Polling до завершения
while true; do
  STATUS=$(curl -s "http://localhost:8000/jobs/$JOB_ID" | jq -r .status)
  echo "status=$STATUS"
  case "$STATUS" in
    success|failed) break ;;
  esac
  sleep 2
done

# Финальный результат
curl -s "http://localhost:8000/jobs/$JOB_ID" | jq
```

При `status = failed` смотрите поле `error` в ответе `GET /jobs/{id}`.

---

## Доступные источники

Поддерживаемые источники: `github`, `reddit`, `hackernews`, `arxiv`.

Актуальный список всегда возвращает `GET /health` в поле `sources` — именно эти
значения можно передавать в `source` при `POST /jobs`. Любое другое значение
приведёт к ошибке `400`.
