# Модель данных find-engine

## Введение

find-engine использует **гибридную модель хранения** в PostgreSQL, разделяющую данные по назначению:

- **`items`** — нормализованная таблица для поиска и аналитики. Содержит унифицированный набор полей, по которым внешний софт строит выборки и фильтры.
- **`raw_records`** — сырые ответы источников в формате **JSONB**. Хранят полный исходный payload на случай, если нормализованная схема чего-то не покрывает.
- **`jobs`** — управление сбором: состояние прогонов, инкрементальность (watermark), курсор для resume и статистика.

Все первичные ключи — `UUID`, генерируются на стороне БД функцией `gen_random_uuid()`. Для этого включается расширение **pgcrypto**:

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()
```

Источник правды по схеме: миграция `find_engine/storage/migrations/versions/0001_initial.py` и ORM-модели `find_engine/storage/orm.py`.

---

## Таблица `items`

Нормализованная запись. Дедупликация по паре `(source, external_id)`. Назначение — предоставлять чистые структурированные данные для поиска и аналитики внешним софтом.

| Колонка       | Тип                      | Nullable | Описание |
|---------------|--------------------------|----------|----------|
| `id`          | `UUID`                   | нет      | PK, `gen_random_uuid()` |
| `source`      | `Text`                   | нет      | Идентификатор источника |
| `external_id` | `Text`                   | нет      | ID записи в источнике |
| `title`       | `Text`                   | нет      | Заголовок |
| `url`         | `Text`                   | нет      | Ссылка на оригинал |
| `author`      | `Text`                   | да       | Автор |
| `body`        | `Text`                   | да       | Текст/описание |
| `score`       | `Integer`                | да       | Числовая оценка/рейтинг источника |
| `tags`        | `ARRAY(Text)`            | нет      | Теги, по умолчанию `{}` |
| `created_at`  | `TIMESTAMP(timezone)`    | да       | Дата создания в источнике |
| `fetched_at`  | `TIMESTAMP(timezone)`    | да       | Время сбора |

**Constraints**

- `uq_items_source_external_id` — `UNIQUE (source, external_id)`. Основа дедупликации и upsert-конфликта.

**Индексы**

- `ix_items_source` — по `source` (фильтрация по источнику).
- `ix_items_created_at` — по `created_at` (выборки по дате, инкрементальность).

---

## Таблица `raw_records`

Полный сырой ответ источника. Назначение — сохранить исходный payload без потерь; нормализованный `items` строится поверх него. При каждом повторном сборе записи добавляется **новая** строка (история сырых ответов не перезаписывается).

| Колонка       | Тип                   | Nullable | Описание |
|---------------|-----------------------|----------|----------|
| `id`          | `UUID`                | нет      | PK, `gen_random_uuid()` |
| `item_id`     | `UUID`                | да       | FK → `items.id`, `ON DELETE CASCADE` |
| `source`      | `Text`                | нет      | Идентификатор источника |
| `external_id` | `Text`                | нет      | ID записи в источнике |
| `payload`     | `JSONB`               | нет      | Полный сырой ответ источника |
| `fetched_at`  | `TIMESTAMP(timezone)` | да       | Время сбора |

**Связи**

- `item_id` → `items.id` с `ondelete=CASCADE`: при удалении `item` каскадно удаляются его сырые записи. На уровне ORM — `relationship(cascade="all, delete-orphan")`.

**Индексы**

- `ix_raw_records_item_id` — по `item_id` (выборка сырых записей конкретного item).

---

## Таблица `jobs`

Состояние задачи сбора по источнику. Хранит per-source watermark (`since`), курсор для возобновления (`cursor`) и статистику (`stats`).

| Колонка       | Тип                   | Nullable | Описание |
|---------------|-----------------------|----------|----------|
| `id`          | `UUID`                | нет      | PK, `gen_random_uuid()` |
| `source`      | `Text`                | нет      | Идентификатор источника |
| `status`      | `String(16)`          | нет      | Состояние, по умолчанию `queued` |
| `since`       | `TIMESTAMP(timezone)` | да       | Watermark — нижняя граница инкрементального сбора |
| `cursor`      | `Text`                | да       | Курсор источника для resume/пагинации |
| `stats`       | `JSONB`               | нет      | Статистика прогона, по умолчанию `{}` |
| `error`       | `Text`                | да       | Текст ошибки (для `failed`) |
| `started_at`  | `TIMESTAMP(timezone)` | да       | Время старта |
| `finished_at` | `TIMESTAMP(timezone)` | да       | Время завершения |

**Состояния (`status`)**

| Значение  | Смысл |
|-----------|-------|
| `queued`  | Создан, ожидает запуска |
| `running` | Выполняется |
| `success` | Успешно завершён |
| `failed`  | Завершён с ошибкой (см. `error`) |

В коде состояния определены перечислением `JobState` (`find_engine/core/models.py`). Поле `stats` сериализуется из `JobStats` и содержит счётчики `fetched`, `inserted`, `updated`, `skipped`.

**Индексы**

- `ix_jobs_source_status` — составной по `(source, status)`. Используется в запросах вида «последний успешный прогон источника».

---

## Связь pydantic-моделей и ORM

Логика приложения оперирует pydantic-моделями (`find_engine/core/models.py`), персистентность — ORM-классами (`find_engine/storage/orm.py`).

| Pydantic     | ORM            | Назначение |
|--------------|----------------|------------|
| `Item`       | `ItemORM`      | Нормализованная запись |
| `RawRecord`  | `RawRecordORM` | Сырой payload |
| `Job`        | `JobORM`       | Задача сбора |

- `Item` / `RawRecord` не имеют `id` — он назначается БД при upsert/insert; pydantic-модели описывают только бизнес-поля.
- `Job` несёт `id` (default `uuid4`) и вложенную `JobStats`.
- Конвертация `JobORM → Job` выполняется хелпером **`_job_from_orm`** (`repository.py`): он маппит колонки, приводит `status` к `JobState` и разворачивает `stats` обратно в `JobStats(**(orm.stats or {}))`.

---

## Дедупликация и upsert

Метод `Repository.upsert_item` (`find_engine/storage/repository.py`) выполняет вставку с разрешением конфликта по уникальному ключу `(source, external_id)`:

```python
pg_insert(ItemORM)
    .values(**values)
    .on_conflict_do_update(
        index_elements=["source", "external_id"],
        set_={...},  # title, url, author, body, score, tags, created_at, fetched_at
    )
    .returning(ItemORM.id, (ItemORM.xmax == 0).label("inserted"))
```

- **Конфликт** по `(source, external_id)` → существующая строка `items` **обновляется** значениями нового сбора (`ON CONFLICT DO UPDATE`).
- **Признак inserted vs updated** определяется по системной колонке PostgreSQL **`xmax`**: для свежевставленной строки `xmax == 0` (вставка), для обновлённой — `xmax != 0` (апдейт). Метод возвращает `(item_id, inserted: bool)`.
- При повторном сборе один и тот же `item` **обновляется на месте** (одна строка на `(source, external_id)`), а в `raw_records` при переданном `payload` **добавляется новая запись** — так копится история сырых ответов.

Счётчики `inserted` / `updated` агрегируются вызывающим кодом в `JobStats` и сохраняются в `jobs.stats`.

---

## Watermark / инкрементальность

Инкрементальный сбор опирается на метод `Repository.last_successful_watermark(source)`:

```sql
SELECT finished_at FROM jobs
WHERE source = :source AND status = 'success'
ORDER BY finished_at DESC
LIMIT 1;
```

- **`last_successful_watermark`** = `finished_at` последнего job со `status = success` по данному источнику.
- Это значение становится **`since`** для следующего прогона: новый сбор запрашивает у источника только записи, появившиеся после предыдущего успешного завершения.
- `cursor` дополняет watermark для постраничного возобновления в пределах одного прогона.

---

## На будущее

Схема спроектирована с расчётом на **семантический поиск через pgvector**:

- нормализованный `items` (с `title` / `body`) — естественный носитель эмбеддингов: достаточно добавить колонку типа `vector` и индекс (HNSW/IVFFlat);
- `raw_records.payload` (JSONB) сохраняет полный контекст для построения и обновления векторов без повторного сбора.

В версии v1 семантический поиск **не используется** — это задел на будущее; текущая схема к нему готова без переноса данных.
