"""Тесты чистых функций формулы скоринга (Фаза 2).

Только чистая логика — никаких БД, сети, asyncio.
"""

from __future__ import annotations

import pytest

from analysis.score.formula import (
    assign_tier,
    compute_coefficient,
    load_scoring_config,
    should_escalate,
)
from analysis.score.models import ScoreParams, ScoreResult, ScoringConfig


# ---------------------------------------------------------------------------
# Вспомогательные фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture()
def default_config() -> ScoringConfig:
    return ScoringConfig.default()


def _params(
    relevance: float = 0.5,
    complexity: float = 0.5,
    novelty: float = 0.5,
    maturity: float = 0.5,
    potential: float = 0.5,
) -> ScoreParams:
    return ScoreParams(
        relevance=relevance,
        complexity=complexity,
        novelty=novelty,
        maturity=maturity,
        potential=potential,
    )


def _result(confidence: float = 0.9, params: ScoreParams | None = None) -> ScoreResult:
    return ScoreResult(
        params=params or _params(),
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# compute_coefficient
# ---------------------------------------------------------------------------

class TestComputeCoefficient:
    """Тесты формулы коэффициента."""

    def test_known_vector_matches_hand_calculation(self, default_config: ScoringConfig) -> None:
        """Известный вектор параметров даёт ожидаемый коэффициент.

        Формула: bias + 0.45*0.8 + 0.20*0.6 + 0.20*0.7 + (-0.10)*0.3 + (-0.15)*0.4
               = 0.15 + 0.36 + 0.12 + 0.14 - 0.03 - 0.06 = 0.68
        """
        params = _params(relevance=0.8, complexity=0.3, novelty=0.6, maturity=0.4, potential=0.7)
        coef = compute_coefficient(params, default_config)
        assert abs(coef - 0.68) < 1e-9

    def test_higher_complexity_lowers_coefficient(self, default_config: ScoringConfig) -> None:
        """Рост complexity (издержка) снижает коэффициент."""
        low = compute_coefficient(_params(complexity=0.1), default_config)
        high = compute_coefficient(_params(complexity=0.9), default_config)
        assert high < low

    def test_higher_maturity_lowers_coefficient(self, default_config: ScoringConfig) -> None:
        """Рост maturity (издержка) снижает коэффициент."""
        low = compute_coefficient(_params(maturity=0.1), default_config)
        high = compute_coefficient(_params(maturity=0.9), default_config)
        assert high < low

    def test_higher_relevance_raises_coefficient(self, default_config: ScoringConfig) -> None:
        """Рост relevance (выгода) повышает коэффициент."""
        low = compute_coefficient(_params(relevance=0.1), default_config)
        high = compute_coefficient(_params(relevance=0.9), default_config)
        assert high > low

    def test_clamp_to_one_on_extreme_positive(self) -> None:
        """Коэффициент не превышает 1.0 при экстремальных положительных значениях."""
        # bias=0.5 + weight*1.0 = 1.5 -> должно зажаться в 1.0
        config = ScoringConfig(
            weights={"relevance": 1.0},
            bias=0.5,
            tier_thresholds=[("S", 0.8), ("D", 0.0)],
            escalate_min_confidence=0.5,
            escalate_high_coefficient=0.95,
            escalate_boundary_margin=0.03,
        )
        coef = compute_coefficient(_params(relevance=1.0), config)
        assert coef == 1.0

    def test_clamp_to_zero_on_extreme_negative(self) -> None:
        """Коэффициент не опускается ниже 0.0 при экстремальных отрицательных значениях."""
        # bias=-0.5 + 0 weights = -0.5 -> должно зажаться в 0.0
        config = ScoringConfig(
            weights={},
            bias=-0.5,
            tier_thresholds=[("S", 0.8), ("D", 0.0)],
            escalate_min_confidence=0.5,
            escalate_high_coefficient=0.95,
            escalate_boundary_margin=0.03,
        )
        coef = compute_coefficient(_params(), config)
        assert coef == 0.0

    def test_all_ones_default_config(self, default_config: ScoringConfig) -> None:
        """Все параметры = 1.0: raw = 0.15+0.45+0.20+0.20-0.10-0.15 = 0.75."""
        coef = compute_coefficient(_params(1.0, 1.0, 1.0, 1.0, 1.0), default_config)
        assert abs(coef - 0.75) < 1e-9

    def test_all_zeros_default_config(self, default_config: ScoringConfig) -> None:
        """Все параметры = 0.0: коэффициент = bias = 0.15."""
        coef = compute_coefficient(_params(0.0, 0.0, 0.0, 0.0, 0.0), default_config)
        assert abs(coef - 0.15) < 1e-9

    def test_missing_weight_treated_as_zero(self) -> None:
        """Параметр без веса в config.weights не влияет на коэффициент."""
        config = ScoringConfig(
            weights={"relevance": 0.5},  # остальные отсутствуют
            bias=0.0,
            tier_thresholds=[("D", 0.0)],
            escalate_min_confidence=0.5,
            escalate_high_coefficient=0.9,
            escalate_boundary_margin=0.02,
        )
        coef = compute_coefficient(_params(relevance=0.4, complexity=1.0), config)
        assert abs(coef - 0.2) < 1e-9  # 0 + 0.5*0.4 = 0.2


# ---------------------------------------------------------------------------
# assign_tier
# ---------------------------------------------------------------------------

class TestAssignTier:
    """Тесты назначения тира по коэффициенту."""

    @pytest.mark.parametrize("coef,expected_tier", [
        # Прямо на пороге → тот же тир (>= семантика)
        (0.80, "S"),
        (0.65, "A"),
        (0.50, "B"),
        (0.35, "C"),
        (0.00, "D"),
        # Чуть выше порога → верхний тир
        (0.81, "S"),
        (0.66, "A"),
        (0.51, "B"),
        (0.36, "C"),
        (0.01, "D"),
        # Чуть ниже порога → следующий тир вниз
        (0.799, "A"),
        (0.649, "B"),
        (0.499, "C"),
        (0.349, "D"),
    ])
    def test_tier_assignment(
        self, coef: float, expected_tier: str, default_config: ScoringConfig
    ) -> None:
        assert assign_tier(coef, default_config) == expected_tier

    def test_tier_flips_around_threshold(self, default_config: ScoringConfig) -> None:
        """Тир меняется именно на пороге, не раньше и не позже."""
        just_above = assign_tier(0.800001, default_config)
        on_threshold = assign_tier(0.80, default_config)
        just_below = assign_tier(0.799999, default_config)
        assert just_above == "S"
        assert on_threshold == "S"
        assert just_below == "A"

    def test_empty_tier_thresholds_returns_D(self) -> None:
        """Пустой список порогов → 'D' как безопасный fallback."""
        config = ScoringConfig(
            weights={},
            bias=0.0,
            tier_thresholds=[],
            escalate_min_confidence=0.5,
            escalate_high_coefficient=0.9,
            escalate_boundary_margin=0.02,
        )
        assert assign_tier(0.9, config) == "D"


# ---------------------------------------------------------------------------
# should_escalate
# ---------------------------------------------------------------------------

class TestShouldEscalate:
    """Тесты условий эскалации."""

    def test_escalate_on_low_confidence(self, default_config: ScoringConfig) -> None:
        """Только низкая уверенность → эскалация."""
        # escalate_min_confidence=0.55; coefficient=0.5 (не high, не на границе)
        result = _result(confidence=0.40)
        assert should_escalate(result, 0.50, default_config) is True

    def test_escalate_on_high_coefficient(self, default_config: ScoringConfig) -> None:
        """Только высокий коэффициент → эскалация."""
        # escalate_high_coefficient=0.80; confidence=0.9 (выше min); не на границе
        result = _result(confidence=0.90)
        assert should_escalate(result, 0.90, default_config) is True

    def test_escalate_on_boundary_margin(self, default_config: ScoringConfig) -> None:
        """Только нахождение на границе тира → эскалация.

        Порог A = 0.65; margin = 0.03; coefficient = 0.66 (distance = 0.01 <= 0.03).
        confidence = 0.9 (выше min_confidence=0.55); coef=0.66 < high=0.80.
        """
        result = _result(confidence=0.90)
        coef = 0.66  # |0.66 - 0.65| = 0.01 <= 0.03
        assert should_escalate(result, coef, default_config) is True

    def test_no_escalate_when_no_condition_met(self, default_config: ScoringConfig) -> None:
        """Ни одно условие не выполнено → нет эскалации.

        confidence = 0.9 > 0.55; coef = 0.55 < 0.80;
        ближайший порог: B=0.50, |0.55-0.50|=0.05 > margin=0.03.
        """
        result = _result(confidence=0.90)
        coef = 0.55
        assert should_escalate(result, coef, default_config) is False

    def test_exactly_at_escalate_high_coefficient_boundary(
        self, default_config: ScoringConfig
    ) -> None:
        """coef == escalate_high_coefficient → эскалация (>= семантика)."""
        result = _result(confidence=0.90)
        assert should_escalate(result, 0.80, default_config) is True

    def test_exactly_at_confidence_boundary(self, default_config: ScoringConfig) -> None:
        """confidence == escalate_min_confidence → НЕТ эскалации (< семантика).

        coef = 0.55 (не high, не на границе тира).
        """
        result = _result(confidence=0.55)
        assert should_escalate(result, 0.55, default_config) is False


# ---------------------------------------------------------------------------
# load_scoring_config
# ---------------------------------------------------------------------------

class TestLoadScoringConfig:
    """Тесты загрузки конфигурации из настроек."""

    def test_returns_default_when_no_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """При отсутствии override-полей в Settings возвращается ScoringConfig.default()."""
        import unittest.mock as mock

        defaults = ScoringConfig.default()

        # Подменяем get_settings чистой заглушкой без scoring-полей
        class _MinimalSettings:
            pass

        with mock.patch("analysis.config.get_settings", return_value=_MinimalSettings()):
            config = load_scoring_config()

        assert config.weights == defaults.weights
        assert config.bias == defaults.bias
        assert config.tier_thresholds == defaults.tier_thresholds
        assert config.escalate_min_confidence == defaults.escalate_min_confidence
        assert config.escalate_high_coefficient == defaults.escalate_high_coefficient
        assert config.escalate_boundary_margin == defaults.escalate_boundary_margin

    def test_returns_default_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Возвращаемое значение — экземпляр ScoringConfig."""
        import unittest.mock as mock

        class _MinimalSettings:
            pass

        with mock.patch("analysis.config.get_settings", return_value=_MinimalSettings()):
            config = load_scoring_config()

        assert isinstance(config, ScoringConfig)

    def test_json_string_weights_are_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JSON-строка в scoring_weights корректно парсится."""
        import unittest.mock as mock

        class _SettingsWithJsonWeights:
            scoring_weights = '{"relevance": 0.9, "novelty": 0.1}'

        with mock.patch("analysis.config.get_settings", return_value=_SettingsWithJsonWeights()):
            config = load_scoring_config()

        assert abs(config.weights["relevance"] - 0.9) < 1e-9
        assert abs(config.weights["novelty"] - 0.1) < 1e-9

    def test_invalid_json_weights_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """При невалидном JSON в scoring_weights используется default."""
        import unittest.mock as mock

        class _SettingsWithBadWeights:
            scoring_weights = "{not: valid json}"

        defaults = ScoringConfig.default()
        with mock.patch("analysis.config.get_settings", return_value=_SettingsWithBadWeights()):
            config = load_scoring_config()

        assert config.weights == defaults.weights

    def test_json_string_tiers_are_parsed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """JSON-строка в scoring_tiers корректно парсится."""
        import unittest.mock as mock

        tiers_json = '[["X", 0.9], ["Y", 0.0]]'

        class _SettingsWithJsonTiers:
            scoring_tiers = tiers_json

        with mock.patch("analysis.config.get_settings", return_value=_SettingsWithJsonTiers()):
            config = load_scoring_config()

        assert config.tier_thresholds == [("X", 0.9), ("Y", 0.0)]

    def test_float_overrides_are_applied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Числовые поля escalation применяются из Settings."""
        import unittest.mock as mock

        class _SettingsWithEscalation:
            escalate_min_confidence = 0.70
            escalate_high_coefficient = 0.95
            escalate_boundary_margin = 0.05

        with mock.patch("analysis.config.get_settings", return_value=_SettingsWithEscalation()):
            config = load_scoring_config()

        assert abs(config.escalate_min_confidence - 0.70) < 1e-9
        assert abs(config.escalate_high_coefficient - 0.95) < 1e-9
        assert abs(config.escalate_boundary_margin - 0.05) < 1e-9
