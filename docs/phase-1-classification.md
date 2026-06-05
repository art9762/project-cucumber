# Фаза 1 — классификация items по дереву категорий

Спека для реализации (swarm, TDD). Цель: новые `items` раскладываются по
seed-дереву категорий дешёвой моделью (Haiku через Trinity); модель может
предложить новую подкатегорию, которая создаётся **неутверждённой** и ждёт
ручного утверждения. Результат пишется в `item_analysis` (`category_id`,
`model_used`, `analyzed_at`), прогон — в `analysis_runs` (`kind="classify"`).

Опирается на каркас Фазы 0 ([`phase-0-analysis-scaffold.md`](phase-0-analysis-scaffold.md))
и общий план ([`analysis-plan.md`](analysis-plan.md)). Схема БД уже готова —
**миграции не нужны**: `categories.approved`, `item_analysis.category_id`,
`analysis_runs.kind` уже существуют.

## Definition of Done

- [ ] Новый item получает строку в `item_analysis` с непустым `category_id`
      (существующая утверждённая категория) и `model_used`.
- [ ] Модель может предложить подкатегорию → создаётся узел `categories` с
      `approved=False` под выбранным родителем. Item привязывается к **родителю**
      (утверждённому), не к неутверждённой ветке.
- [ ] Идемпотентность: повторный прогон не трогает уже классифицированные items
      (работает через `select_new_items`).
- [ ] Прогон фиксируется в `analysis_runs` (kind=`classify`, status, stats, время).
- [ ] Ошибка по одному item не валит весь прогон (item → `failed`, ошибка в stats).
- [ ] API: дерево категорий, список «на утверждение», approve/reject, запуск прогона.
- [ ] `pytest`/`ruff`/`mypy` зелёные. Trinity мокается, БД-тесты на SQLite (conftest).

## Контракт (зафиксирован — НЕ менять сигнатуры)

Общий dataclass-контракт уже написан в `analysis/classify/models.py`:

```python
@dataclass(frozen=True)
class CategoryNode:
    id: uuid.UUID
    slug: str
    title: str
    parent_id: uuid.UUID | None
    approved: bool

@dataclass(frozen=True)
class ClassificationResult:
    category_slug: str
    confidence: float
    suggested_subcategory_slug: str | None = None
    suggested_subcategory_title: str | None = None
    @property
    def has_suggestion(self) -> bool: ...

@dataclass
class ClassifyStats:
    seen: int = 0
    classified: int = 0
    suggested: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    def as_dict(self) -> dict[str, object]: ...
```

### `analysis/classify/prompt.py` (чистые функции, без I/O)

```python
def build_classify_prompt(
    item: ItemReadORM,
    categories: list[CategoryNode],
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для Trinity.complete(...).
    Перечисляет утверждённые верхнеуровневые категории (slug + title),
    просит выбрать ровно один slug и опционально предложить подкатегорию.
    Требует от модели ответ строго JSON-объектом."""

def parse_classification(text: str) -> ClassificationResult:
    """Распарсить ответ модели (JSON, возможно в ```-блоке или с мусором по краям).
    Валидирует confidence в [0,1] (клампит). Если подкатегория указана частично
    (slug без title или наоборот) — обнуляет обе. slug нормализуется в kebab-case.
    Бросает ValueError, если нет валидного category_slug."""
```

Ожидаемый JSON-ответ модели:
```json
{"category": "ai", "confidence": 0.9,
 "suggested_subcategory": {"slug": "llm-agents", "title": "LLM-агенты"}}
```
`suggested_subcategory` может быть `null`.

### `analysis/classify/categories.py` (репозиторий дерева; analysis-сессия = запись)

```python
async def load_category_tree(session: AsyncSession) -> list[CategoryNode]:
    """Все категории (любой approved) как список CategoryNode."""

async def load_approved_top_level(session: AsyncSession) -> list[CategoryNode]:
    """Только approved=True и parent_id IS NULL — кандидаты для промпта."""

async def get_by_slug(session: AsyncSession, slug: str) -> CategoryNode | None:
    """Категория по slug или None."""

async def ensure_subcategory(
    session: AsyncSession, *, parent_slug: str, slug: str, title: str,
) -> CategoryNode:
    """Идемпотентно вернуть/создать подкатегорию под parent_slug.
    Новая создаётся approved=False. Если slug уже есть — вернуть существующую
    (не дублировать). НЕ commit'ит — это делает вызывающий."""

async def list_pending(session: AsyncSession) -> list[CategoryNode]:
    """Неутверждённые категории (approved=False) — очередь на утверждение."""

async def set_approved(
    session: AsyncSession, category_id: uuid.UUID, approved: bool,
) -> CategoryNode | None:
    """Утвердить (True) / отклонить-флагом (False). Вернуть обновлённый узел
    или None, если не найден. НЕ commit'ит."""

async def delete_category(session: AsyncSession, category_id: uuid.UUID) -> bool:
    """Удалить узел (для reject). True, если удалён. НЕ commit'ит."""
```

### `analysis/classify/classifier.py` (оркестратор)

```python
async def run_classification(
    *,
    read_sessionmaker: async_sessionmaker[AsyncSession],
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    limit: int | None = None,
    model: str | None = None,
) -> ClassifyStats:
    """Полный прогон классификации одного батча новых items.

    1. analysis_runs ← новая строка kind='classify', status='running', started_at.
    2. select_new_items(read_session, limit) — новые items.
    3. Для каждого item:
       - build_classify_prompt(item, approved_top_level)
       - text = await trinity.complete(messages, model=model, system=system)
       - res = parse_classification(text)
       - категория = get_by_slug(res.category_slug); если нет → 'other'.
       - если res.has_suggestion: ensure_subcategory(parent=res.category_slug,
         slug/title из res) → approved=False; stats.suggested += 1.
         (item всё равно привязывается к РОДИТЕЛЮ — утверждённому.)
       - INSERT item_analysis(item_id, category_id=<родитель>, model_used).
       - stats.classified += 1.
       - любое исключение по item → stats.failed += 1, stats.errors.append(...),
         продолжаем со следующего.
    4. analysis_runs ← status='success' (или 'failed' при фатале), finished_at,
       stats=stats.as_dict().
    Вернуть ClassifyStats.

    Замечания:
    - item_analysis пишем своей analysis-сессией; items читаем read-сессией.
    - не писать в items/raw_records/jobs.
    """
```

`analysis/classify/__main__.py` — CLI: `python -m analysis.classify [--limit N]`
поднимает sessionmaker'ы и trinity из конфига, печатает stats JSON.

### `analysis/api/category_schemas.py` (НОВЫЙ файл — не трогать api/schemas.py)

Pydantic-схемы: `CategoryOut`, `CategoryTreeNode` (рекурсивный children),
`ClassifyRunOut` (по полям ClassifyStats), `ApproveResponse`.

### `analysis/api/routers/categories.py` (НОВЫЙ роутер)

```
GET  /categories             → дерево (approved + pending), вложенный children
GET  /categories/pending     → список неутверждённых (очередь модерации)
POST /categories/{id}/approve→ approved=True
POST /categories/{id}/reject → удалить узел (delete_category)
POST /classify               → запустить run_classification (limit из query/body),
                               вернуть ClassifyRunOut
```
Использует `get_analysis_session` / `get_analysis_sessionmaker` из storage/db,
`get_trinity_client` из trinity. Роутер регистрируется в `main.py` интегратором.

## Тестирование (как в Фазе 0)

- `tests/test_prompt.py` — чистые функции, без БД/сети. Парсинг: чистый JSON,
  JSON в ```-блоке, мусор по краям, частичная подкатегория, плохой confidence,
  отсутствие категории → ValueError.
- `tests/test_categories.py` — на `analysis_sessionmaker` (conftest, SQLite).
  Сидинг категорий вручную (в SQLite миграции не гоняются). Проверить
  ensure_subcategory идемпотентность, approved=False по умолчанию, list_pending,
  set_approved, delete_category.
- `tests/test_classifier.py` — `analysis_sessionmaker` + замоканный TrinityClient
  (AsyncMock.complete возвращает JSON-строку). Проверить: пишется item_analysis,
  category_id = родитель, suggestion создаёт unapproved-узел, идемпотентность
  (второй прогон seen=0), ошибка парсинга по одному item → failed без падения
  всего прогона, analysis_runs фиксируется.
- `tests/test_categories_api.py` — FastAPI TestClient с override зависимостей на
  conftest-sessionmaker; classify-роут с замоканным trinity. (Если override
  сложен — допустимо мокать слой categories/classifier.)

conftest уже даёт `analysis_sessionmaker` (SQLite, схема items + analysis-таблиц,
before_insert проставляет UUID/время). Сиди категории прямо в тесте через
`CategoryORM(...)`.

## Запрет (как в Фазе 0)
Не писать в таблицы движка, не импортировать ORM движка, секреты только из env,
файлы < 500 строк, без `Co-Authored-By`. Коммит/пуш — только по просьбе пользователя.
