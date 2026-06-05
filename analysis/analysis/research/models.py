"""Контракт Фазы 3 (research) — зафиксирован, НЕ менять сигнатуры.

Веб-разбор выбранной идеи: дешёвый/глубокий проход через серверный web_search
Trinity даёт сводку, список конкурентов и сигналы зрелости/потенциала, которыми
скоринг (Фаза 2) может уточнить оценку.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Competitor:
    """Найденный в вебе конкурент/похожее решение."""

    name: str
    url: str | None = None
    note: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"name": self.name, "url": self.url, "note": self.note}


@dataclass(frozen=True)
class ResearchResult:
    """Результат веб-разбора одного item.

    ``maturity_signal``/``potential_signal`` — 0..1 или None: насколько тема уже
    реализована (зрелость) и насколько перспективна (потенциал) по веб-данным.
    ``sources`` — URL, на которые опирался разбор.
    """

    summary: str
    competitors: list[Competitor] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    maturity_signal: float | None = None
    potential_signal: float | None = None
    confidence: float = 0.5

    def competitors_as_dicts(self) -> list[dict[str, str | None]]:
        return [c.as_dict() for c in self.competitors]


@dataclass
class ResearchStats:
    """Статистика прогона ресёрча (по аналогии с ClassifyStats/ScoreStats)."""

    seen: int = 0
    researched: int = 0
    competitors_found: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "seen": self.seen,
            "researched": self.researched,
            "competitors_found": self.competitors_found,
            "failed": self.failed,
            "errors": self.errors,
        }
