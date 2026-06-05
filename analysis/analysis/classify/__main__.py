"""CLI точка входа: python -m analysis.classify [--limit N] [--model NAME].

Поднимает sessionmaker'ы и trinity из конфига, запускает run_classification,
печатает stats.as_dict() как JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from analysis.classify.classifier import run_classification
from analysis.storage.db import get_analysis_sessionmaker, get_read_sessionmaker
from analysis.trinity import get_trinity_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Запустить классификацию новых items.")
    parser.add_argument("--limit", type=int, default=None, help="Максимальное число items.")
    parser.add_argument("--model", type=str, default=None, help="Имя модели (переопределить cheap).")
    return parser.parse_args()


async def _main() -> None:
    args = _parse_args()
    stats = await run_classification(
        read_sessionmaker=get_read_sessionmaker(),
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=args.limit,
        model=args.model,
    )
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
