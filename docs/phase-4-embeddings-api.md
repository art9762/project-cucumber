# Фаза 4 — эмбеддинги + analysis API

Спека для реализации (swarm, TDD). Цель: **векторизовать items** локальной
моделью (fastembed, CPU — без внешнего API), хранить векторы в `item_embeddings`
(pgvector), и поверх дать **семантический поиск** и **поиск конкурентов** (опиши
решение → похожие из базы по косинусу), а также добить HTTP API анализа.

Trinity эмбеддингов НЕ даёт (проверено — 404). Эмбеддинги считаем **локально**
через `fastembed` (`BAAI/bge-small-en-v1.5`, dim=384, CPU). Postgres должен быть
с **pgvector** (интегратор меняет образ движка на `pgvector/pgvector:pg16`).

Схема БД готова интегратором: таблица `item_embeddings` + расширение `vector`
созданы миграцией `0002_research_embeddings` (**миграции писать НЕ нужно**). ORM
`ItemEmbeddingORM` (колонка `embedding` — pgvector `vector(384)` на PG, JSON на
SQLite) и `EMBEDDING_DIM=384` уже в `storage/orm.py`.

## Definition of Done

- [ ] Для item создаётся строка `item_embeddings` с вектором dim=384, `model`,
      `dim`. Текст для эмбеддинга = title + (обрезанное) body.
- [ ] Идемпотентность: повторный прогон не трогает уже векторизованные items
      (`select_unembedded_items` — нет строки item_embeddings).
- [ ] Прогон фиксируется в `analysis_runs` (kind=`embed`, status, stats, время).
- [ ] Ошибка по одному item не валит прогон (item → `failed`, ошибка в stats).
- [ ] Семантический поиск: по тексту запроса → top-K ближайших items (косинус).
      На Postgres — через pgvector `<=>`; в unit-тестах (SQLite) — Python-side
      косинус (фолбэк), чтобы тесты не требовали Postgres.
- [ ] API: умный поиск, поиск конкурентов по item, запуск эмбеддинга, дерево
      категорий, подбор по категории. `pytest`/`ruff`/`mypy` зелёные.

## Контракт (зафиксирован — НЕ менять) — `analysis/embed/models.py`

Уже написан интегратором:

```python
@dataclass
class EmbedStats:
    seen=0; embedded=0; failed=0; model: str|None; dim: int|None; errors: list[str]
    def as_dict(self) -> dict[str, object]: ...

@dataclass(frozen=True)
class SearchHit:
    item_id: str; title: str; url: str
    distance: float; similarity: float
    tier: str|None=None; coefficient: float|None=None; category_id: str|None=None
```

`EMBEDDING_DIM = 384` импортировать из `analysis.storage.orm`.

### `analysis/embed/encoder.py` (обёртка модели) — АГЕНТ A

```python
class Encoder:
    """Локальный энкодер текста в вектор (fastembed, ленивая загрузка модели)."""
    def __init__(self, model_name: str | None = None) -> None:
        """model_name None → get_settings().embedding_model. Модель НЕ грузить в
        __init__ — лениво при первом encode (тяжёлая загрузка весов)."""
    @property
    def model_name(self) -> str: ...
    @property
    def dim(self) -> int: ...        # EMBEDDING_DIM
    def encode(self, text: str) -> list[float]:
        """Один текст → вектор float (длина dim). Пустой текст → нулевой вектор."""
    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Батч текстов → список векторов (порядок сохранён)."""

def build_embed_text(item: ItemReadORM) -> str:
    """title + '\\n\\n' + body[:2000] (обрезка как в prompt-модулях). None body → ''."""

def cosine_distance(a: list[float], b: list[float]) -> float:
    """Косинусная дистанция 1 - (a·b)/(|a||b|). Нулевой вектор → 1.0.
    Используется в SQLite-фолбэке поиска (на PG — оператор <=>)."""
```

fastembed: `from fastembed import TextEmbedding; m = TextEmbedding(model_name);
list(m.embed([text]))[0].tolist()`. Грузить модель один раз (кэш в self).

Тесты `tests/test_encoder.py`: **fastembed мокать** (не качать веса в CI) —
пропатчить загрузчик так, чтобы encode возвращал детерминированный вектор нужной
длины; проверить dim, encode_batch сохраняет порядок, build_embed_text
обрезает/склеивает, cosine_distance (идентичные=0, ортогональные≈1, нулевой=1).
Допустимо: если мок сложен — тестировать build_embed_text/cosine_distance как
чистые функции, а Encoder.encode — на инъекции фейкового model-объекта.

### `analysis/embed/selector.py` (БД-чтение) — АГЕНТ B

```python
async def select_unembedded_items(
    session: AsyncSession,   # analysis-сессия: items LEFT JOIN item_embeddings
    *,
    limit: int | None = None,
) -> list[ItemReadORM]:
    """Items без строки item_embeddings. Порядок: fetched_at ASC, id ASC.
    limit по умолчанию из Settings.analysis_batch_size. (Эмбеддим ВСЕ items, а
    не только классифицированные — вектор полезен независимо.)"""
```

LEFT JOIN `ItemEmbeddingORM` по item_id, фильтр `ItemEmbeddingORM.id IS NULL`.

### `analysis/embed/embedder.py` + `__main__.py` (оркестратор) — АГЕНТ B

```python
async def run_embedding(
    *,
    read_sessionmaker: async_sessionmaker[AsyncSession],
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    encoder: Encoder,
    limit: int | None = None,
) -> EmbedStats:
    """Прогон эмбеддинга батча невекторизованных items. Зеркало classifier.py
    (нужны ОБА sessionmaker'а: items читаем read-сессией, item_embeddings пишем
    analysis-сессией):
    1. analysis_runs ← kind='embed', status='running', started_at (commit сразу).
    2. items = select_unembedded_items(analysis_session, limit)  # на одной БД обе
       таблицы видны; читать можно analysis-сессией (как scorer).
    3. texts = [build_embed_text(it) for it in items]; vecs = encoder.encode_batch(texts).
    4. Для каждого (item, vec) внутри begin_nested() SAVEPOINT:
       INSERT ItemEmbeddingORM(item_id, embedding=vec, model=encoder.model_name,
       dim=encoder.dim); stats.embedded += 1. Исключение → failed += 1.
    5. stats.model/dim проставить; analysis_runs ← success/failed, finished_at, stats.
    Вернуть EmbedStats.
    Примечание: батч-энкод ВНЕ savepoint (CPU-bound, без БД); запись — внутри.
    Допустимо использовать analysis_sessionmaker и для чтения items (как scorer.py
    использует одну сессию) — read_sessionmaker принять для единообразия сигнатур."""
```

`__main__.py` — CLI `python -m analysis.embed [--limit N] [--model NAME]`.
Поднять sessionmaker'ы + Encoder из конфига, печать stats JSON. Зеркало
`score/__main__.py`.

Тесты `tests/test_embedder.py` (на `analysis_sessionmaker`, **фейковый Encoder**
— объект с .encode_batch → детерминированные векторы, .model_name/.dim): сид
items; проверить — пишется item_embeddings (вектор сохранён как список,
model/dim), идемпотентность (второй прогон seen=0), per-item failure не валит,
analysis_runs kind='embed' success.

### `analysis/embed/search.py` (поиск) — АГЕНТ C

```python
async def search_by_vector(
    session: AsyncSession,
    query_vec: list[float],
    *,
    limit: int = 10,
    exclude_item_id: uuid.UUID | None = None,
) -> list[SearchHit]:
    """top-K ближайших items по косинусу к query_vec.
    На Postgres: ORDER BY item_embeddings.embedding <=> query_vec LIMIT k,
    JOIN items (+ LEFT JOIN item_analysis для tier/coefficient/category_id).
    На SQLite (тесты): подтянуть все векторы, посчитать cosine_distance в Python,
    отсортировать, взять k. Определять диалект по session.bind.dialect.name.
    distance = косинус-дистанция, similarity = 1 - distance.
    exclude_item_id — исключить сам item (для поиска конкурентов по item)."""

async def search_by_text(
    session: AsyncSession, encoder: "Encoder", query: str, *, limit: int = 10,
) -> list[SearchHit]:
    """encoder.encode(query) → search_by_vector. (encoder импортировать лениво/
    через тип, чтобы не тянуть fastembed в модулях без него.)"""

async def find_competitors(
    session: AsyncSession, item_id: uuid.UUID, *, limit: int = 10,
) -> list[SearchHit]:
    """Взять вектор item_id из item_embeddings → search_by_vector(exclude=item_id).
    Если у item нет вектора → пустой список."""
```

Тесты `tests/test_search.py` (на `analysis_sessionmaker`, SQLite-ветка): сид
несколько item_embeddings с заданными векторами; проверить — search_by_vector
возвращает по близости (ближайший первый), similarity=1-distance, exclude_item_id
исключает, find_competitors по item возвращает других, у item без вектора пусто.

### `analysis/api/search_schemas.py` (НОВЫЙ файл) — АГЕНТ D

Pydantic: `SearchHitOut` (item_id, title, url, distance, similarity, tier,
coefficient, category_id), `EmbedRunOut` (по полям EmbedStats), `SearchQueryIn`
(query: str, limit: int = 10) для POST-боди умного поиска.

### `analysis/api/routers/search.py` (НОВЫЙ роутер) — АГЕНТ D

```
POST /search            {query, limit}  → list[SearchHitOut] (умный поиск по тексту)
GET  /items/{id}/competitors?limit=     → list[SearchHitOut] (поиск конкурентов)
POST /embed?limit=                      → run_embedding, EmbedRunOut
```

Использует `get_analysis_session`/`get_analysis_sessionmaker`,
`get_read_sessionmaker`. Encoder — ленивый синглтон внутри роутера (модуль-уровень
`_encoder` + геттер, или Depends) — НЕ грузить при импорте. POST /search и
/embed лениво импортируют embed.search/embed.embedder/embed.encoder.
`router = APIRouter(tags=["search"])`. Регистрируется в `main.py` ИНТЕГРАТОРОМ.

Тесты `tests/test_search_api.py`: TestClient override get_analysis_session;
сид item_embeddings; POST /search мокнуть encoder (фикс. вектор) → проверить
сортировку; /items/{id}/competitors; /embed замокать на embedder.run_embedding.

## Запрет
Не писать в таблицы движка, не импортировать ORM движка, секреты только из env,
файлы < 500 строк, без `Co-Authored-By`. Коммит/пуш — только по просьбе.
Не менять `embed/models.py`, `storage/orm.py`, `config.py`, `main.py`, файлы
Фаз 0–3. Интегратор сам правит общие файлы. fastembed в тестах НЕ грузить —
мокать.
```
