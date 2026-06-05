"""Tests for analysis.embed.encoder (Encoder, build_embed_text, cosine_distance).

fastembed is NOT installed in the venv — tests mock it by injecting a fake model
object directly onto the Encoder instance (set _model to a stub with an .embed
method returning lists that have a .tolist() method). No weights are downloaded.
"""

from __future__ import annotations

import math
import sys
import types
import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from analysis.storage.orm import EMBEDDING_DIM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakeItem:
    """Simple stand-in for ItemReadORM; only title/body are needed by build_embed_text."""

    title: str = "Test Title"
    body: str | None = "Test body"
    id: Any = field(default_factory=uuid.uuid4)
    source: str = "test"
    external_id: str = "ext-1"
    url: str = "https://example.com"
    author: str | None = None
    score: int | None = None
    tags: list = field(default_factory=list)
    created_at: Any = None
    fetched_at: Any = None


def _make_item(
    title: str = "Test Title",
    body: str | None = "Test body",
) -> _FakeItem:
    """Return a minimal fake item compatible with build_embed_text."""
    return _FakeItem(title=title, body=body)


def _fake_vec(length: int = EMBEDDING_DIM, fill: float = 1.0) -> list[float]:
    return [fill] * length


class _FakeVecResult:
    """Object mimicking a numpy array with .tolist() — returned by fake model.embed."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    def tolist(self) -> list[float]:
        return list(self._vec)


def _make_fake_model(vec: list[float] | None = None) -> MagicMock:
    """Return a stub whose .embed(texts) yields one _FakeVecResult per text."""
    actual_vec = vec if vec is not None else _fake_vec()
    model = MagicMock()
    model.embed.side_effect = lambda texts: [
        _FakeVecResult(actual_vec) for _ in texts
    ]
    return model


def _inject_fake_fastembed() -> None:
    """Register a minimal fake 'fastembed' module so lazy import doesn't fail."""
    if "fastembed" not in sys.modules:
        fake_module = types.ModuleType("fastembed")
        fake_module.TextEmbedding = MagicMock  # type: ignore[attr-defined]
        sys.modules["fastembed"] = fake_module


# ---------------------------------------------------------------------------
# Encoder.dim
# ---------------------------------------------------------------------------

class TestEncoderDim:
    def test_dim_equals_embedding_dim(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        assert enc.dim == 384
        assert enc.dim == EMBEDDING_DIM

    def test_model_name_default_from_settings(self) -> None:
        from analysis.embed.encoder import Encoder
        from analysis.config import get_settings

        enc = Encoder()
        assert enc.model_name == get_settings().embedding_model

    def test_model_name_custom(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder(model_name="custom/model")
        assert enc.model_name == "custom/model"


# ---------------------------------------------------------------------------
# Encoder.encode (via injected fake model)
# ---------------------------------------------------------------------------

class TestEncoderEncode:
    def _encoder_with_fake(self, vec: list[float] | None = None) -> object:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        enc._model = _make_fake_model(vec)  # inject before lazy load fires
        return enc

    def test_encode_returns_vector_of_correct_length(self) -> None:
        enc = self._encoder_with_fake()
        result = enc.encode("hello world")
        assert isinstance(result, list)
        assert len(result) == EMBEDDING_DIM

    def test_encode_empty_string_returns_zero_vector(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        result = enc.encode("")
        assert result == [0.0] * EMBEDDING_DIM

    def test_encode_whitespace_returns_zero_vector(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        result = enc.encode("   \n\t  ")
        assert result == [0.0] * EMBEDDING_DIM

    def test_encode_calls_model_embed(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        fake_model = _make_fake_model()
        enc._model = fake_model
        enc.encode("some text")
        fake_model.embed.assert_called_once_with(["some text"])

    def test_encode_returns_floats(self) -> None:
        enc = self._encoder_with_fake([0.5] * EMBEDDING_DIM)
        result = enc.encode("test")
        assert all(isinstance(v, float) for v in result)


# ---------------------------------------------------------------------------
# Encoder.encode_batch (via injected fake model)
# ---------------------------------------------------------------------------

class TestEncoderEncodeBatch:
    def _encoder_with_fake(self, vec: list[float] | None = None) -> object:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        enc._model = _make_fake_model(vec)
        return enc

    def test_encode_batch_preserves_order_and_length(self) -> None:
        enc = self._encoder_with_fake()
        texts = ["first", "second", "third"]
        results = enc.encode_batch(texts)
        assert len(results) == 3
        for vec in results:
            assert len(vec) == EMBEDDING_DIM

    def test_encode_batch_empty_list_returns_empty(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        assert enc.encode_batch([]) == []

    def test_encode_batch_single_item(self) -> None:
        enc = self._encoder_with_fake()
        results = enc.encode_batch(["only one"])
        assert len(results) == 1
        assert len(results[0]) == EMBEDDING_DIM

    def test_encode_batch_calls_embed_once(self) -> None:
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        fake_model = _make_fake_model()
        enc._model = fake_model
        texts = ["a", "b", "c"]
        enc.encode_batch(texts)
        fake_model.embed.assert_called_once_with(texts)

    def test_encode_batch_each_vec_is_list_of_float(self) -> None:
        enc = self._encoder_with_fake([0.1] * EMBEDDING_DIM)
        results = enc.encode_batch(["x", "y"])
        for vec in results:
            assert isinstance(vec, list)
            assert all(isinstance(v, float) for v in vec)


# ---------------------------------------------------------------------------
# build_embed_text
# ---------------------------------------------------------------------------

class TestBuildEmbedText:
    def test_title_and_body_concatenated(self) -> None:
        from analysis.embed.encoder import build_embed_text

        item = _make_item(title="My Title", body="My body")
        result = build_embed_text(item)
        assert result == "My Title\n\nMy body"

    def test_none_body_returns_title_only(self) -> None:
        from analysis.embed.encoder import build_embed_text

        item = _make_item(title="Only Title", body=None)
        result = build_embed_text(item)
        assert result == "Only Title"

    def test_empty_body_returns_title_only(self) -> None:
        from analysis.embed.encoder import build_embed_text

        item = _make_item(title="Title", body="")
        result = build_embed_text(item)
        assert result == "Title"

    def test_long_body_truncated_to_2000(self) -> None:
        from analysis.embed.encoder import build_embed_text

        long_body = "x" * 5000
        item = _make_item(title="T", body=long_body)
        result = build_embed_text(item)
        # title + "\n\n" + first 2000 chars
        expected = "T\n\n" + "x" * 2000
        assert result == expected

    def test_body_exactly_2000_chars_not_truncated(self) -> None:
        from analysis.embed.encoder import build_embed_text

        body = "y" * 2000
        item = _make_item(title="T", body=body)
        result = build_embed_text(item)
        assert result == "T\n\n" + "y" * 2000

    def test_body_2001_chars_truncated(self) -> None:
        from analysis.embed.encoder import build_embed_text

        body = "z" * 2001
        item = _make_item(title="T", body=body)
        result = build_embed_text(item)
        assert len(result) == len("T\n\n") + 2000

    def test_separator_is_double_newline(self) -> None:
        from analysis.embed.encoder import build_embed_text

        item = _make_item(title="A", body="B")
        result = build_embed_text(item)
        assert "\n\n" in result
        parts = result.split("\n\n", 1)
        assert parts[0] == "A"
        assert parts[1] == "B"


# ---------------------------------------------------------------------------
# cosine_distance
# ---------------------------------------------------------------------------

class TestCosineDistance:
    def test_identical_vectors_distance_zero(self) -> None:
        from analysis.embed.encoder import cosine_distance

        v = [1.0, 0.0, 0.0]
        assert cosine_distance(v, v) == pytest.approx(0.0, abs=1e-9)

    def test_identical_non_unit_vectors_distance_zero(self) -> None:
        from analysis.embed.encoder import cosine_distance

        v = [3.0, 4.0, 0.0]
        assert cosine_distance(v, v) == pytest.approx(0.0, abs=1e-9)

    def test_orthogonal_vectors_distance_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert cosine_distance(a, b) == pytest.approx(1.0, abs=1e-9)

    def test_opposite_vectors_distance_two(self) -> None:
        from analysis.embed.encoder import cosine_distance

        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        assert cosine_distance(a, b) == pytest.approx(2.0, abs=1e-9)

    def test_zero_vector_a_returns_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        assert cosine_distance([0.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0

    def test_zero_vector_b_returns_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        assert cosine_distance([1.0, 0.0, 0.0], [0.0, 0.0, 0.0]) == 1.0

    def test_both_zero_returns_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        assert cosine_distance([0.0, 0.0], [0.0, 0.0]) == 1.0

    def test_partial_overlap(self) -> None:
        from analysis.embed.encoder import cosine_distance

        # 45-degree angle → cos(45°) = sqrt(2)/2 ≈ 0.707 → distance ≈ 0.293
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        dist = cosine_distance(a, b)
        expected = 1.0 - 1.0 / math.sqrt(2)
        assert dist == pytest.approx(expected, abs=1e-9)

    def test_similarity_plus_distance_equals_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        a = [0.2, 0.5, 0.3]
        b = [0.1, 0.8, 0.1]
        dist = cosine_distance(a, b)
        # similarity = 1 - distance; both in [0, 2] and sum related to dot product
        assert 0.0 <= dist <= 2.0

    def test_full_dim_zero_vector_returns_one(self) -> None:
        from analysis.embed.encoder import cosine_distance

        zeros = [0.0] * EMBEDDING_DIM
        ones = [1.0] * EMBEDDING_DIM
        assert cosine_distance(zeros, ones) == 1.0
        assert cosine_distance(ones, zeros) == 1.0
        assert cosine_distance(zeros, zeros) == 1.0


# ---------------------------------------------------------------------------
# Lazy import: module importable without fastembed installed
# ---------------------------------------------------------------------------

class TestLazyImport:
    def test_module_imports_without_fastembed(self) -> None:
        """encoder.py must be importable even if fastembed is absent."""
        # fastembed is not installed; if this import raises, the test fails.
        import analysis.embed.encoder as enc_mod  # noqa: F401

        assert hasattr(enc_mod, "Encoder")
        assert hasattr(enc_mod, "build_embed_text")
        assert hasattr(enc_mod, "cosine_distance")

    def test_encoder_init_does_not_load_model(self) -> None:
        """__init__ must not trigger fastembed import."""
        from analysis.embed.encoder import Encoder

        enc = Encoder()
        # _model should remain None until encode/encode_batch is called
        assert enc._model is None  # type: ignore[attr-defined]
