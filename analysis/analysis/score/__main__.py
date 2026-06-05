"""CLI точка входа: python -m analysis.score [--limit N] [--cheap-model NAME] [--deep-model NAME].

Поднимает analysis sessionmaker и trinity из конфига, запускает run_scoring,
печатает stats.as_dict() как JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from analysis.score.scorer import run_scoring
from analysis.storage.db import get_analysis_sessionmaker
from analysis.trinity import get_trinity_client


def _parse_args() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Запустить скоринг классифицированных items.")
    parser.add_argument("--limit", type=int, default=None, help="Максимальное число items.")
    parser.add_argument("--cheap-model", type=str, default=None, dest="cheap_model",
                        help="Имя дешёвой модели (переопределить).")
    parser.add_argument("--deep-model", type=str, default=None, dest="deep_model",
                        help="Имя глубокой модели (переопределить).")
    return parser.parse_args()


async def _main() -> None:
    """Точка входа async-запуска скоринга."""
    args = _parse_args()
    stats = await run_scoring(
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=args.limit,
        cheap_model=args.cheap_model,
        deep_model=args.deep_model,
    )
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
