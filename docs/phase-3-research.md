# Фаза 3 — research (веб-серч и поиск конкурентов)

Спека для реализации (swarm, TDD). Цель: по выбранной идее (`item`) сделать
**детальный веб-разбор** и **найти конкурентов в вебе**, результат записать в
`item_research`, прогон — в `analysis_runs` (`kind="research"`). Сигналы
зрелости/потенциала из разбора затем уточняют скоринг (Фаза 2).

Веб-поиск идёт через **серверный инструмент Trinity** `web_search_20250305`
(нативный Anthropic web search, проброшен шлюзом — проверено вживую). Внешний
search-провайдер и новые секреты **не нужны**.

Опирается на план ([`analysis-plan.md`](analysis-plan.md)) и Фазы 1–2. Схема БД
готова интегратором: таблица `item_research` создана миграцией
`0002_research_embeddings` (**миграции писать НЕ нужно**). ORM
`ItemResearchORM` уже в `storage/orm.py`.

## Definition of Done

- [ ] Для item создаётся/обновляется строка `item_research`: непустой `summary`,
      список `competitors` (JSONB, объекты `{name,url,note}`), `sources` (URL),
      `maturity_signal`/`potential_signal` (0..1 или None), `model_used`.
- [ ] Веб-поиск реально вызывается (через `TrinityClient.search_complete`).
- [ ] Идемпотентность: повторный прогон не трогает уже разобранные items
      (`select_unresearched_items` — нет строки `item_research` для item).
- [ ] Можно ресёрчить «важные» items: селектор умеет фильтровать по
      `min_tier`/`min_coefficient` (опираясь на `item_analysis`).
- [ ] Прогон фиксируется в `analysis_runs` (kind=`research`, status, stats, время).
- [ ] Ошибка по одному item не валит прогон (item → `failed`, ошибка в stats).
- [ ] API: запуск прогона, получить research одного item, список с конкурентами.
- [ ] `pytest`/`ruff`/`mypy` зелёные. Trinity мокается, БД-тесты на SQLite.

## Контракт (зафиксирован — НЕ менять) — `analysis/research/models.py`

Уже написан интегратором:

```python
@dataclass(frozen=True)
class Competitor:
    name: str; url: str | None = None; note: str | None = None
    def as_dict(self) -> dict[str, str | None]: ...

@dataclass(frozen=True)
class ResearchResult:
    summary: str
    competitors: list[Competitor] = []
    sources: list[str] = []
    maturity_signal: float | None = None
    potential_signal: float | None = None
    confidence: float = 0.5
    def competitors_as_dicts(self) -> list[dict[str, str | None]]: ...

@dataclass
class ResearchStats:
    seen=0; researched=0; competitors_found=0; failed=0; errors: list[str]
    def as_dict(self) -> dict[str, object]: ...
```

`TrinityClient.search_complete(messages, *, model=None, max_tokens=2048,
system=None, max_searches=3) -> tuple[str, list[str]]` — уже реализован
интегратором: возвращает `(text, source_urls)`, текст + URL источников
веб-поиска. **АГЕНТЫ его не трогают, только вызывают.**

### `analysis/research/prompt.py` (чистые функции, без I/O) — АГЕНТ A

```python
def build_research_prompt(
    item: ItemReadORM,
    category_title: str | None = None,
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для TrinityClient.search_complete(...).
    Просит модель: с помощью веб-поиска разобрать идею item — что это, насколько
    тема горячая и зрелая, какие есть конкуренты/похожие продукты (с URL). Затем
    дать СТРОГИЙ JSON: summary (кратко, ~абзац), competitors (список
    {name,url,note}), maturity_signal 0..1, potential_signal 0..1, confidence
    0..1. Тело item обрезать до ~2000 символов (как classify/score prompt:
    скопировать _BODY_MAX_CHARS подход)."""

def parse_research(text: str, sources: list[str]) -> ResearchResult:
    """Распарсить JSON-ответ (raw/fenced/с прозой по краям — переиспользовать
    подход из classify/score prompt: извлечь {...}, json.loads).
    summary: str (обязателен; если пусто/нет — ValueError).
    competitors: список → list[Competitor] (name обязателен, url/note опц.;
    элементы без name пропускать). maturity_signal/potential_signal: float|None,
    кламп [0,1]. confidence: float, кламп [0,1], дефолт 0.5.
    sources прокинуть в ResearchResult.sources (как есть от веб-поиска;
    при желании дополнить URL из competitors)."""
```

Ожидаемый JSON модели:
```json
{"summary": "...", "competitors": [{"name": "Foo", "url": "https://foo.io",
 "note": "ближайший аналог"}], "maturity_signal": 0.6, "potential_signal": 0.7,
 "confidence": 0.8}
```

Тесты `tests/test_research_prompt.py`: чистый JSON, JSON в ```-блоке, мусор по
краям, пустой summary → ValueError, конкурент без name отбрасывается, signal вне
[0,1] клампится, sources прокидываются, длинное body обрезается.

### `analysis/research/selector.py` (БД-чтение) — АГЕНТ B

```python
async def select_unresearched_items(
    session: AsyncSession,   # analysis-сессия: item_analysis + JOIN items, LEFT JOIN item_research
    *,
    limit: int | None = None,
    min_tier: str | None = None,
    min_coefficient: float | None = None,
) -> list[tuple[ItemReadORM, uuid.UUID | None]]:
    """Items, у которых ЕСТЬ строка item_analysis (классифицированы), но НЕТ
    строки item_research (не разобраны). Возвращает пары (item, category_id).
    Фильтры важности: min_tier — оставить только tier ∈ {не хуже min_tier}
    (порядок S>A>B>C>D; «не хуже» = coefficient достаточно высок — проще
    фильтровать по min_coefficient, а min_tier маппить в порог через
    простую карту S=.8/A=.65/B=.5/C=.35/D=0 или сравнивать строки тиров).
    min_coefficient — item_analysis.coefficient >= порога.
    Порядок: item_analysis.coefficient DESC NULLS LAST, items.id —
    важные идеи первыми. limit по умолчанию из Settings.analysis_batch_size."""
```

LEFT JOIN `ItemResearchORM` по `item_id`, фильтр `ItemResearchORM.id IS NULL`.
INNER JOIN `ItemAnalysisORM` (нужна классификация). `ItemReadORM` через
`ItemAnalysisORM.item_id == ItemReadORM.id`.

Тесты `tests/test_research_selector.py` (на `analysis_sessionmaker`): сид
item+item_analysis (с tier/coefficient); проверить — без research-строки попадает
в выборку, с research-строкой не попадает, min_coefficient отсекает слабые,
порядок по coefficient убыв.

### `analysis/research/researcher.py` + `__main__.py` (оркестратор) — АГЕНТ B

```python
async def run_research(
    *,
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    limit: int | None = None,
    min_tier: str | None = None,
    min_coefficient: float | None = None,
    model: str | None = None,        # None → get_settings().research_model
    max_searches: int | None = None, # None → get_settings().research_max_searches
) -> ResearchStats:
    """Полный прогон веб-ресёрча батча неразобранных items. Зеркало
    scorer.py/classifier.py:
    1. analysis_runs ← kind='research', status='running', started_at (commit сразу).
    2. select_unresearched_items(analysis_session, limit, min_tier, min_coefficient).
    3. Для каждого (item, category_id) внутри begin_nested() SAVEPOINT:
       - system, messages = build_research_prompt(item, category_title=None)
       - text, sources = await trinity.search_complete(messages, model=model,
         system=system, max_searches=max_searches_eff)
       - res = parse_research(text, sources)
       - INSERT ItemResearchORM(item_id, summary=res.summary,
         competitors=res.competitors_as_dicts(), sources=res.sources,
         maturity_signal=res.maturity_signal, potential_signal=res.potential_signal,
         model_used=<модель>).
       - stats.researched += 1; stats.competitors_found += len(res.competitors).
       - исключение → stats.failed += 1, stats.errors.append, continue.
    4. analysis_runs ← status='success'/'failed', finished_at, stats=as_dict().
    Вернуть ResearchStats.

    НЕ писать в items/raw_records/jobs; вставляем НОВУЮ строку item_research
    (1:1 к item; идемпотентность обеспечивает селектор)."""
```

`__main__.py` — CLI `python -m analysis.research [--limit N] [--min-tier S]
[--min-coefficient F] [--model NAME] [--max-searches N]`. Зеркало
`score/__main__.py`: поднять analysis_sessionmaker + trinity, печать stats JSON.
Дефолт модели — `get_settings().research_model`.

Тесты `tests/test_researcher.py` (на `analysis_sessionmaker`, мок TrinityClient
с `search_complete` AsyncMock → `("...json...", ["https://src"])`): сид
item+item_analysis; проверить — пишется item_research (summary/competitors/
sources/model_used), идемпотентность (второй прогон seen=0), per-item failure не
валит прогон, analysis_runs зафиксирован kind='research' status='success'.

### `analysis/api/research_schemas.py` (НОВЫЙ файл) — АГЕНТ C

Pydantic: `CompetitorOut` (name,url,note), `ItemResearchOut` (item_id, title,
url, summary, competitors: list[CompetitorOut], sources: list[str],
maturity_signal, potential_signal, model_used), `ResearchRunOut` (по полям
ResearchStats: seen/researched/competitors_found/failed/errors).

### `analysis/api/routers/research.py` (НОВЫЙ роутер) — АГЕНТ C

```
GET  /items/{item_id}/research   → ItemResearchOut (404 если нет)
GET  /research?has_competitors=  → список ItemResearchOut (опц. фильтр: только с
                                   непустыми competitors), limit
POST /research?limit=&min_tier=&min_coefficient=  → run_research, ResearchRunOut
```

Использует `get_analysis_session`/`get_analysis_sessionmaker`,
`get_trinity_client` (ленивый импорт researcher/trinity в POST — как в
scores.py /score). `router = APIRouter(tags=["research"])`. Регистрируется в
`main.py` ИНТЕГРАТОРОМ (агент main.py НЕ трогает).

Тесты `tests/test_research_api.py`: TestClient с override get_analysis_session на
conftest-sessionmaker; засидить item_research; /items/{id}/research 200 и 404,
/research отдаёт и фильтрует. POST можно замокать на уровне researcher.run_research.

## Запрет
Не писать в таблицы движка, не импортировать ORM движка, секреты только из env,
файлы < 500 строк, без `Co-Authored-By`. Коммит/пуш — только по просьбе.
Не менять `research/models.py`, `trinity.py`, `storage/orm.py`, `config.py`,
`main.py`, файлы Фаз 0–2. Интегратор сам правит общие файлы.
