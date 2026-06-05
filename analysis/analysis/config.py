"""Конфигурация из окружения (.env). Секреты — только отсюда, никогда из кода.

Паттерн повторяет движок (`find_engine/config.py`): pydantic-settings + lru_cache.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Дефолтный DSN общей с движком БД. Read-роль по умолчанию совпадает с основной
# (раздельные права — задел на Фазу 6).
_DEFAULT_DB = "postgresql+asyncpg://analysis:analysis@localhost:5432/findengine"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Database (общая с движком). DB_URL_READ — read-only к таблицам движка,
    # DB_URL_ANALYSIS — полные права на свои таблицы. По умолчанию совпадают.
    db_url_analysis: str = _DEFAULT_DB
    db_url_read: str = _DEFAULT_DB

    # Trinity (Anthropic-совместимый шлюз). Токен — только из env.
    anthropic_auth_token: str | None = None
    anthropic_base_url: str = "https://gate.trinity.tg/aurora"
    analysis_model_cheap: str = "claude-haiku-4-5"
    analysis_model_deep: str = "claude-sonnet-4-6"

    # Обработка
    analysis_batch_size: int = 50

    # Скоринг (Фаза 2) — переопределения формулы и порогов из env. None → берётся
    # ScoringConfig.default() в analysis.score.formula.load_scoring_config().
    # weights/tiers принимаются как JSON-строки (env-переменные — строки):
    #   SCORING_WEIGHTS='{"relevance":0.45,"complexity":-0.10,...}'
    #   SCORING_TIERS='[["S",0.80],["A",0.65],["B",0.50],["C",0.35],["D",0.0]]'
    scoring_weights: str | None = None
    scoring_bias: float | None = None
    scoring_tiers: str | None = None
    escalate_min_confidence: float | None = None
    escalate_high_coefficient: float | None = None
    escalate_boundary_margin: float | None = None

    @property
    def read_url_effective(self) -> str:
        """Read-DSN; падает обратно на analysis-DSN, если read не задан отдельно."""
        return self.db_url_read or self.db_url_analysis


@lru_cache
def get_settings() -> Settings:
    return Settings()
