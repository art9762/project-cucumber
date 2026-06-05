# Фаза 2 — скоринг и тирлист

Спека для реализации (swarm, TDD). Цель: классифицированные `items` получают
пять параметров оценки (актуальность/сложность/новизна/зрелость/потенциал) от
модели, из них по **формуле из конфига** считается коэффициент, по порогам —
тир **S/A/B/C/D**. Спорные/важные идеи **эскалируются** на глубокую модель
(Sonnet). Результат пишется в `item_analysis` (`scores` JSONB, `coefficient`
Float, `tier` String(1)), прогон — в `analysis_runs` (`kind="score"`).

Опирается на Фазу 1 ([`phase-1-classification.md`](phase-1-classification.md)) и
общий план ([`analysis-plan.md`](analysis-plan.md)). Схема БД уже готова —
**миграции не нужны**: `item_analysis.scores`, `.coefficient`, `.tier` уже
существуют (nullable-задел из Фазы 0).

## Definition of Done

- [ ] Классифицированный item (есть строка `item_analysis`) получает непустые
      `scores` (5 параметров 0..1), `coefficient` (float), `tier` (S/A/B/C/D).
- [ ] Коэффициент считается формулой из `ScoringConfig` (веса/bias/пороги — из
      конфига, можно переоценить без перезапуска кода).
- [ ] Спорные/важные идеи эскалируются на deep-модель и пересчитываются.
- [ ] Идемпотентность: повторный прогон не трогает уже оценённые items
      (`select_unscored_items` — есть category_id, но нет coefficient).
- [ ] Прогон фиксируется в `analysis_runs` (kind=`score`, status, stats, время).
- [ ] Ошибка по одному item не валит прогон (item → `failed`, ошибка в stats).
- [ ] API: тирлист с фильтрами, оценка одного item, запуск прогона.
- [ ] `pytest`/`ruff`/`mypy` зелёные. Trinity мокается, БД-тесты на SQLite.

## Контракт (зафиксирован — НЕ менять сигнатуры)

Общий dataclass-контракт уже написан в `analysis/score/models.py`:

```python
PARAM_NAMES = ("relevance", "complexity", "novelty", "maturity", "potential")

@dataclass(frozen=True)
class ScoreParams:
    relevance: float; complexity: float; novelty: float
    maturity: float; potential: float
    def as_dict(self) -> dict[str, float]: ...   # {name: value} в порядке PARAM_NAMES

@dataclass(frozen=True)
class ScoreResult:
    params: ScoreParams
    confidence: float
    rationale: str | None = None

@dataclass(frozen=True)
class ScoringConfig:
    weights: dict[str, float]          # знаковые: relevance/novelty/potential +, complexity/maturity -
    bias: float
    tier_thresholds: list[tuple[str, float]]   # по убыванию порога, последний порог = 0.0
    escalate_min_confidence: float
    escalate_high_coefficient: float
    escalate_boundary_margin: float
    @classmethod
    def default(cls) -> "ScoringConfig": ...

@dataclass
class ScoreStats:
    seen=0; scored=0; escalated=0; failed=0
    tier_counts: dict[str,int]; errors: list[str]
    def record_tier(self, tier: str) -> None: ...
    def as_dict(self) -> dict[str, object]: ...
```

Каждый параметр 0.0–1.0. Коэффициент = `clamp01(bias + Σ weights[k]·param_k)`.
`complexity`/`maturity` имеют отрицательные веса — это издержки.

### `analysis/score/prompt.py` (чистые функции, без I/O) — АГЕНТ A

```python
def build_score_prompt(
    item: ItemReadORM,
    category_title: str | None = None,
) -> tuple[str, list[dict]]:
    """Вернуть (system_prompt, messages) для TrinityClient.complete(messages, system=...).
    Просит модель оценить item по 5 параметрам (relevance/complexity/novelty/
    maturity/potential), каждый 0.0–1.0, дать confidence 0..1 и краткое
    rationale. Требует строгий JSON. Тело item обрезать до ~2000 символов
    (как в classify/prompt.py — скопировать _BODY_MAX_CHARS и подход)."""

def parse_scores(text: str) -> ScoreResult:
    """Распарсить JSON-ответ (raw/fenced/с прозой по краям — переиспользовать
    подход из classify/prompt.py: извлечь {...}, json.loads).
    Каждый из 5 параметров: float, кламп в [0,1], при отсутствии/ошибке → 0.5.
    confidence: float, кламп [0,1], дефолт 0.5. rationale: str|None (обрезать
    ~500 символов). Если JSON не парсится вообще → ValueError."""
```

Ожидаемый JSON-ответ модели:
```json
{"relevance": 0.9, "complexity": 0.4, "novelty": 0.7, "maturity": 0.3,
 "potential": 0.8, "confidence": 0.85, "rationale": "горячая тема, мало решений"}
```

Тесты `tests/test_score_prompt.py`: чистый JSON, JSON в ```-блоке, мусор по
краям, отсутствующий параметр → 0.5, confidence вне [0,1] → кламп, полностью
битый текст → ValueError, длинное rationale обрезается, длинное body обрезается.

### `analysis/score/formula.py` (чистые функции, без I/O) — АГЕНТ B

```python
def compute_coefficient(params: ScoreParams, config: ScoringConfig) -> float:
    """clamp01(config.bias + Σ config.weights[name] · getattr(params, name)).
    Параметры без веса в config.weights игнорируются (вес 0)."""

def assign_tier(coefficient: float, config: ScoringConfig) -> str:
    """Первый tier из config.tier_thresholds (по убыванию порога), чей порог
    <= coefficient. Гарантированно вернёт тир (последний порог 0.0)."""

def should_escalate(result: ScoreResult, coefficient: float, config: ScoringConfig) -> bool:
    """True, если идею надо перепроверить глубокой моделью:
    - result.confidence < config.escalate_min_confidence, ИЛИ
    - coefficient >= config.escalate_high_coefficient (важная), ИЛИ
    - coefficient в пределах config.escalate_boundary_margin от любого порога
      тира (спорная, на границе)."""

def load_scoring_config() -> ScoringConfig:
    """Собрать ScoringConfig из настроек. Если в Settings нет полей переопределения
    (scoring_weights/scoring_bias/scoring_tiers/escalate_*) — вернуть
    ScoringConfig.default(). Интегратор добавит поля в config.py; до этого
    использовать get_settings() через getattr с дефолтами, НЕ падать."""
```

Тесты `tests/test_formula.py`: коэффициент с дефолт-конфигом (проверить знаки —
рост complexity/maturity снижает коэффициент), кламп в [0,1], assign_tier на
границах каждого порога, should_escalate по каждому из трёх условий по
отдельности, load_scoring_config возвращает дефолт без env.

### `analysis/score/selector.py` (БД-чтение) — АГЕНТ C

```python
async def select_unscored_items(
    session: AsyncSession,   # analysis-сессия: читаем item_analysis + JOIN items
    *,
    limit: int | None = None,
) -> list[tuple[ItemReadORM, uuid.UUID | None]]:
    """Items, у которых ЕСТЬ строка item_analysis с category_id, но coefficient
    IS NULL (классифицированы, но не оценены). Возвращает пары
    (item, category_id). Порядок: items.fetched_at ASC, items.id ASC.
    limit по умолчанию из Settings.analysis_batch_size (как select_new_items)."""
```

Примечание: и `items`, и `item_analysis` доступны на одной analysis-сессии
(в тестовой SQLite — один движок; в Postgres analysis-DSN видит обе). JOIN
`ItemAnalysisORM.item_id == ItemReadORM.id`, фильтр
`ItemAnalysisORM.category_id IS NOT NULL AND ItemAnalysisORM.coefficient IS NULL`.

### `analysis/score/scorer.py` + `__main__.py` (оркестратор) — АГЕНТ C

```python
async def run_scoring(
    *,
    analysis_sessionmaker: async_sessionmaker[AsyncSession],
    trinity: TrinityClient,
    config: ScoringConfig | None = None,   # None → load_scoring_config()
    limit: int | None = None,
    cheap_model: str | None = None,
    deep_model: str | None = None,
) -> ScoreStats:
    """Полный прогон скоринга батча неоценённых items.

    1. analysis_runs ← новая строка kind='score', status='running', started_at
       (commit сразу, как в classifier.py).
    2. select_unscored_items(analysis_session, limit).
    3. Для каждого (item, category_id) внутри begin_nested() SAVEPOINT:
       - system, messages = build_score_prompt(item, category_title)
         (category_title можно не резолвить — допустимо передать None в MVP).
       - text = await trinity.complete(messages, model=cheap_model, system=system)
       - res = parse_scores(text)
       - coef = compute_coefficient(res.params, config)
       - если should_escalate(res, coef, config) и deep_model доступна:
           повторить complete(model=deep_model), parse_scores, пересчитать coef;
           stats.escalated += 1; model_used = deep_model.
       - tier = assign_tier(coef, config)
       - UPDATE item_analysis SET scores=res.params.as_dict(), coefficient=coef,
         tier=tier, model_used=<использованная модель> WHERE item_id=item.id.
       - stats.scored += 1; stats.record_tier(tier).
       - любое исключение → stats.failed += 1, stats.errors.append, continue.
    4. analysis_runs ← status='success'/'failed', finished_at, stats=as_dict().
    Вернуть ScoreStats.

    Замечания: НЕ писать в items/raw_records/jobs; обновляем СУЩЕСТВУЮЩУЮ строку
    item_analysis (она создана Фазой 1), не вставляем новую."""
```

`analysis/score/__main__.py` — CLI: `python -m analysis.score [--limit N]
[--cheap-model NAME] [--deep-model NAME]`. Поднимает analysis_sessionmaker и
trinity из конфига, печатает stats JSON. Зеркало `classify/__main__.py`.

Дефолт моделей: `cheap_model` → `get_settings().analysis_model_cheap`,
`deep_model` → `get_settings().analysis_model_deep`.

Тесты `tests/test_scorer.py` (на `analysis_sessionmaker`, мок TrinityClient):
сидим категорию + item + СТРОКУ item_analysis (category_id задан, coefficient
None — имитируем выход Фазы 1). Проверить: scores/coefficient/tier проставлены,
идемпотентность (второй прогон seen=0), per-item failure не валит прогон,
эскалация (низкий confidence → trinity.complete вызван дважды, model_used =
deep), analysis_runs зафиксирован kind='score' status='success'.

### `analysis/api/score_schemas.py` (НОВЫЙ файл) — АГЕНТ D

Pydantic: `TierItemOut` (item_id, title, url, category_id, tier, coefficient,
scores: dict[str,float]), `TierlistOut` (или просто `list[TierItemOut]`),
`ItemScoreOut` (детали одного item), `ScoreRunOut` (по полям ScoreStats:
seen/scored/escalated/failed/tier_counts/errors).

### `analysis/api/routers/scores.py` (НОВЫЙ роутер) — АГЕНТ D

```
GET  /tierlist?tier=S&category_id=...&limit=...  → отсортированный по coefficient
                                                    DESC список TierItemOut
GET  /items/{item_id}/score                       → ItemScoreOut (404 если нет)
POST /score?limit=...                             → запустить run_scoring, ScoreRunOut
```

Тирлист: JOIN item_analysis + items, фильтр по tier/category_id опционально,
только строки с coefficient IS NOT NULL, ORDER BY coefficient DESC. Использует
`get_analysis_session`/`get_analysis_sessionmaker`, `get_trinity_client`
(ленивый импорт scorer/trinity в POST — как в categories.py /classify).
Роутер регистрируется в `main.py` интегратором.

Тесты `tests/test_scores_api.py`: TestClient с override get_analysis_session на
conftest-sessionmaker; засидить item_analysis со scores/tier; проверить
/tierlist отдаёт и фильтрует, /items/{id}/score 200 и 404. POST /score можно
замокать на уровне scorer.

## Запрет (как в Фазах 0–1)
Не писать в таблицы движка, не импортировать ORM движка, секреты только из env,
файлы < 500 строк, без `Co-Authored-By`. Коммит/пуш — только по просьбе.
Не менять сигнатуры из `score/models.py`. Не трогать `api/schemas.py` и файлы
Фазы 1 (classify/*, categories router). Интегратор сам правит `config.py` и
`main.py` — агенты их НЕ трогают.
```
