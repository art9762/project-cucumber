"""Абстракция Source + реестр плагинов.

Добавить источник = написать класс по протоколу Source и зарегистрировать его.
Ядро при этом не меняется.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from find_engine.core.models import Item, RawRecord


@runtime_checkable
class Source(Protocol):
    """Контракт источника.

    `fetch` тянет только новое с момента `since` (инкрементальный добор);
    `cursor` — для resume/пагинации внутри одного запуска.
    `normalize` приводит сырой ответ к единой модели Item.
    """

    name: str

    def fetch(
        self, since: datetime | None, cursor: str | None
    ) -> AsyncIterator[RawRecord]: ...

    def normalize(self, raw: RawRecord) -> Item: ...


_REGISTRY: dict[str, Source] = {}


def register(source: Source) -> Source:
    """Зарегистрировать инстанс источника по его `name`."""
    if source.name in _REGISTRY:
        raise ValueError(f"Source already registered: {source.name}")
    _REGISTRY[source.name] = source
    return source


def get_source(name: str) -> Source:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"Unknown source: {name!r}. Registered: {sorted(_REGISTRY)}")


def available_sources() -> list[str]:
    return sorted(_REGISTRY)


def clear_registry() -> None:
    """Только для тестов."""
    _REGISTRY.clear()
