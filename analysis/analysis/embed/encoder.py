"""Encoder — локальный энкодер текста в вектор (fastembed, ленивая загрузка).

Фаза 4: векторизация items локальной моделью (CPU, без внешнего API).
fastembed импортируется лениво внутри метода, чтобы модуль загружался без
установленного пакета (CI, импорт без весов).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from analysis.config import get_settings
from analysis.storage.orm import EMBEDDING_DIM, ItemReadORM

if TYPE_CHECKING:
    pass

# Максимальная длина body для текста эмбеддинга (зеркало _BODY_MAX_CHARS в prompt.py).
_BODY_MAX_CHARS = 2000


class Encoder:
    """Локальный энкодер текста в вектор (fastembed, ленивая загрузка модели)."""

    def __init__(self, model_name: str | None = None) -> None:
        """model_name None → get_settings().embedding_model.

        Модель НЕ грузится в __init__ — лениво при первом encode.
        """
        self._model_name: str = model_name or get_settings().embedding_model
        self._model: object | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM

    def _get_model(self) -> object:
        """Ленивая загрузка и кэш TextEmbedding."""
        if self._model is None:
            from fastembed import TextEmbedding  # noqa: PLC0415

            self._model = TextEmbedding(self._model_name)
        return self._model

    def encode(self, text: str) -> list[float]:
        """Один текст → вектор float (длина dim). Пустой текст → нулевой вектор."""
        if not text or not text.strip():
            return [0.0] * self.dim
        model = self._get_model()
        vecs = list(model.embed([text]))  # type: ignore[attr-defined]
        return vecs[0].tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        """Батч текстов → список векторов (порядок сохранён)."""
        if not texts:
            return []
        model = self._get_model()
        vecs = list(model.embed(texts))  # type: ignore[attr-defined]
        return [v.tolist() for v in vecs]


def build_embed_text(item: ItemReadORM) -> str:
    """title + '\\n\\n' + body[:2000]. None body → только title."""
    body = item.body or ""
    if not body:
        return item.title
    return item.title + "\n\n" + body[:_BODY_MAX_CHARS]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Косинусная дистанция 1 - (a·b)/(|a||b|). Нулевой вектор → 1.0."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)
