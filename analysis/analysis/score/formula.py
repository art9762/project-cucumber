"""Чистые функции формулы коэффициента, тиров и эскалации (Фаза 2).

Никакого I/O — кроме ``load_scoring_config``, которая читает настройки один раз.
Все функции детерминированы и тестируемы в изоляции.
"""

from __future__ import annotations

import json
import logging

from analysis.score.models import PARAM_NAMES, ScoreParams, ScoreResult, ScoringConfig

logger = logging.getLogger(__name__)


def compute_coefficient(params: ScoreParams, config: ScoringConfig) -> float:
    """Вычислить коэффициент и зажать в [0, 1].

    Формула: ``clamp01(config.bias + Σ config.weights.get(name, 0.0) * param)``.
    Параметры, отсутствующие в ``config.weights``, дают нулевой вклад.
    """
    raw = config.bias + sum(
        config.weights.get(name, 0.0) * float(getattr(params, name))
        for name in PARAM_NAMES
    )
    return max(0.0, min(1.0, raw))


def assign_tier(coefficient: float, config: ScoringConfig) -> str:
    """Вернуть тир для коэффициента по убывающему списку порогов.

    Возвращает первый тир, чей порог ``<= coefficient`` (список уже отсортирован
    по убыванию порога). Последний элемент имеет порог ``0.0``, поэтому тир
    всегда найдётся. Если список почему-то пуст — возвращает ``'D'``.
    """
    for tier, threshold in config.tier_thresholds:
        if threshold <= coefficient:
            return tier
    return "D"


def should_escalate(
    result: ScoreResult,
    coefficient: float,
    config: ScoringConfig,
) -> bool:
    """Проверить, нужно ли эскалировать item на более глубокую модель.

    Возвращает ``True``, если выполнено ХОТЯ БЫ ОДНО из условий:

    - ``result.confidence < config.escalate_min_confidence`` — модель не уверена;
    - ``coefficient >= config.escalate_high_coefficient`` — высокая ценность;
    - ``coefficient`` находится в пределах ``escalate_boundary_margin`` от любого
      порога тира (спорный результат на границе тира).
    """
    if result.confidence < config.escalate_min_confidence:
        return True
    if coefficient >= config.escalate_high_coefficient:
        return True
    margin = config.escalate_boundary_margin
    for _tier, threshold in config.tier_thresholds:
        if abs(coefficient - threshold) <= margin:
            return True
    return False


def load_scoring_config() -> ScoringConfig:
    """Построить ``ScoringConfig`` из ``analysis.config.get_settings()``.

    Поля скоринга могут ещё отсутствовать в ``Settings`` (интегратор добавит
    позже), поэтому используем ``getattr(..., None)`` и падаем обратно на
    значения из ``ScoringConfig.default()``. Не бросает исключений при
    отсутствии полей.

    Принимаемые поля (все опциональные):
    ``scoring_weights``, ``scoring_bias``, ``scoring_tiers``,
    ``escalate_min_confidence``, ``escalate_high_coefficient``,
    ``escalate_boundary_margin``.

    JSON-строки для ``scoring_weights`` и ``scoring_tiers`` парсятся
    автоматически (env-переменные — строки); при ошибке парсинга
    используется значение из ``default()``.
    """
    from analysis.config import get_settings  # локальный импорт — избегаем цикла

    settings = get_settings()
    defaults = ScoringConfig.default()

    # --- weights ---
    weights = defaults.weights
    raw_weights = getattr(settings, "scoring_weights", None)
    if raw_weights is not None:
        if isinstance(raw_weights, str):
            try:
                raw_weights = json.loads(raw_weights)
            except (json.JSONDecodeError, ValueError):
                logger.warning("scoring_weights: ошибка парсинга JSON, используем default")
                raw_weights = None
        if isinstance(raw_weights, dict):
            weights = {str(k): float(v) for k, v in raw_weights.items()}

    # --- bias ---
    raw_bias = getattr(settings, "scoring_bias", None)
    bias: float = float(raw_bias) if raw_bias is not None else defaults.bias

    # --- tier_thresholds ---
    tier_thresholds = defaults.tier_thresholds
    raw_tiers = getattr(settings, "scoring_tiers", None)
    if raw_tiers is not None:
        if isinstance(raw_tiers, str):
            try:
                raw_tiers = json.loads(raw_tiers)
            except (json.JSONDecodeError, ValueError):
                logger.warning("scoring_tiers: ошибка парсинга JSON, используем default")
                raw_tiers = None
        if isinstance(raw_tiers, list):
            try:
                tier_thresholds = [(str(t), float(v)) for t, v in raw_tiers]
            except (TypeError, ValueError):
                tier_thresholds = defaults.tier_thresholds

    # --- escalation fields ---
    def _float_or(field: str, default: float) -> float:
        val = getattr(settings, field, None)
        return float(val) if val is not None else default

    return ScoringConfig(
        weights=weights,
        bias=bias,
        tier_thresholds=tier_thresholds,
        escalate_min_confidence=_float_or(
            "escalate_min_confidence", defaults.escalate_min_confidence
        ),
        escalate_high_coefficient=_float_or(
            "escalate_high_coefficient", defaults.escalate_high_coefficient
        ),
        escalate_boundary_margin=_float_or(
            "escalate_boundary_margin", defaults.escalate_boundary_margin
        ),
    )
