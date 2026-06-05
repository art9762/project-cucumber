"""CLI точка входа: python -m analysis.embed [--limit N] [--model NAME].

Поднимает read/analysis sessionmaker'ы из конфига, строит Encoder, запускает
run_embedding, печатает stats.as_dict() как JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from analysis.embed.embedder import run_embedding
from analysis.storage.db import get_analysis_sessionmaker, get_read_sessionmaker


def _parse_args() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Запустить эмбеддинг items.")
    parser.add_argument("--limit", type=int, default=None, help="Максимальное число items.")
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Имя модели эмбеддинга (переопределить).",
    )
    return parser.parse_args()


async def _amain() -> None:
    """Точка входа async-запуска эмбеддинга."""
    args = _parse_args()

    # Encoder импортируется лениво, чтобы fastembed не грузился при импорте модуля.
    from analysis.embed.encoder import Encoder  # noqa: PLC0415

    encoder = Encoder(model_name=args.model)

    stats = await run_embedding(
        read_sessionmaker=get_read_sessionmaker(),
        analysis_sessionmaker=get_analysis_sessionmaker(),
        encoder=encoder,
        limit=args.limit,
    )
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_amain())
