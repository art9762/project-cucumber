"""Контракт данных Фазы 2 (скоринг и тирлист).

Чистые dataclass'ы без зависимостей на ORM/SDK — общий язык между слоями:
парсер промпта, формула коэффициента и оркестратор обмениваются этими типами.

Пять параметров (каждый 0.0–1.0, выставляет модель):

- ``relevance``  — актуальность: насколько тема горячая сейчас (выше = горячее).
- ``complexity`` — сложность реализации (выше = труднее; это ИЗДЕРЖКА).
- ``novelty``    — новизна: насколько идея незаезженная (выше = новее).
- ``maturity``   — зрелость: насколько уже реализовано/есть продукт
  (выше = рынок насыщеннее; это ИЗДЕРЖКА для поиска новых возможностей).
- ``potential``  — потенциал: рынок / применимость (выше = больше).

Коэффициент = ``clamp01(bias + Σ weights[k] · param_k)``. Веса ЗНАКОВЫЕ:
relevance/novelty/potential положительные, complexity/maturity отрицательные.
Веса, bias и пороги тиров живут в :class:`ScoringConfig` (из конфига), чтобы
переоценивать без перезапуска кода.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Канонический порядок параметров — единый источник правды для всех слоёв.
PARAM_NAMES: tuple[str, ...] = ("relevance", "complexity", "novelty", "maturity", "potential")


@dataclass(frozen=True)
class ScoreParams:
    """Пять параметров оценки одного item (каждый 0.0–1.0)."""

    relevance: float
    complexity: float
    novelty: float
    maturity: float
    potential: float

    def as_dict(self) -> dict[str, float]:
        """JSON-совместимый словарь {имя_параметра: значение} в каноническом порядке."""
        return {name: float(getattr(self, name)) for name in PARAM_NAMES}


@dataclass(frozen=True)
class ScoreResult:
    """Результат скоринга одного item, разобранный из ответа модели.

    Attributes:
        params: Пять параметров (0.0–1.0).
        confidence: Уверенность модели в оценке 0.0–1.0.
        rationale: Краткое обоснование от модели (опционально, для аудита).
    """

    params: ScoreParams
    confidence: float
    rationale: str | None = None


@dataclass(frozen=True)
class ScoringConfig:
    """Конфигурация формулы коэффициента и порогов тиров (из конфига/env).

    Attributes:
        weights: Знаковые веса параметров {имя: вес}. Положительные — выгоды
            (relevance/novelty/potential), отрицательные — издержки
            (complexity/maturity).
        bias: Базовое смещение коэффициента (сдвигает диапазон в [0, 1]).
        tier_thresholds: Список ``(tier, min_coefficient)``, отсортированный по
            порогу УБЫВАЮЩЕ. Первый тир, чей порог ``<= coefficient``, и есть
            результат. Последний элемент — нижний тир с порогом ``-inf``/``0``.
        escalate_min_confidence: Эскалировать, если confidence модели НИЖЕ.
        escalate_high_coefficient: Эскалировать, если coefficient НЕ НИЖЕ
            (важная/высокая идея — перепроверяем глубокой моделью).
        escalate_boundary_margin: Эскалировать, если coefficient ближе этого
            к любому порогу тира (спорный, на границе).
    """

    weights: dict[str, float]
    bias: float
    tier_thresholds: list[tuple[str, float]]
    escalate_min_confidence: float
    escalate_high_coefficient: float
    escalate_boundary_margin: float

    @classmethod
    def default(cls) -> "ScoringConfig":
        """Дефолтная конфигурация: актуальность доминирует; издержки вычитаются."""
        return cls(
            weights={
                "relevance": 0.45,
                "novelty": 0.20,
                "potential": 0.20,
                "complexity": -0.10,
                "maturity": -0.15,
            },
            bias=0.15,
            tier_thresholds=[
                ("S", 0.80),
                ("A", 0.65),
                ("B", 0.50),
                ("C", 0.35),
                ("D", 0.0),
            ],
            escalate_min_confidence=0.55,
            escalate_high_coefficient=0.80,
            escalate_boundary_margin=0.03,
        )


@dataclass
class ScoreStats:
    """Агрегированная статистика прогона скоринга (пишется в analysis_runs.stats)."""

    seen: int = 0
    scored: int = 0
    escalated: int = 0
    failed: int = 0
    tier_counts: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def record_tier(self, tier: str) -> None:
        """Инкрементировать счётчик тира."""
        self.tier_counts[tier] = self.tier_counts.get(tier, 0) + 1

    def as_dict(self) -> dict[str, object]:
        """JSON-совместимый словарь для analysis_runs.stats."""
        return {
            "seen": self.seen,
            "scored": self.scored,
            "escalated": self.escalated,
            "failed": self.failed,
            "tier_counts": self.tier_counts,
            "errors": self.errors,
        }
