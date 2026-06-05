"""CLI точка входа: python -m analysis.research [--limit N] [--min-tier S] ...

Поднимает analysis sessionmaker и trinity из конфига, запускает run_research,
печатает stats.as_dict() как JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from analysis.research.researcher import run_research
from analysis.storage.db import get_analysis_sessionmaker
from analysis.trinity import get_trinity_client


def _parse_args() -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(description="Запустить веб-ресёрч неразобранных items.")
    parser.add_argument("--limit", type=int, default=None, help="Максимальное число items.")
    parser.add_argument("--min-tier", type=str, default=None, dest="min_tier",
                        help="Минимальный тир (S/A/B/C/D).")
    parser.add_argument("--min-coefficient", type=float, default=None, dest="min_coefficient",
                        help="Минимальный coefficient (0..1).")
    parser.add_argument("--model", type=str, default=None,
                        help="Имя модели (переопределить research_model из Settings).")
    parser.add_argument("--max-searches", type=int, default=None, dest="max_searches",
                        help="Максимум поисков на item (переопределить research_max_searches).")
    return parser.parse_args()


async def _main() -> None:
    """Точка входа async-запуска ресёрча."""
    args = _parse_args()
    stats = await run_research(
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=args.limit,
        min_tier=args.min_tier,
        min_coefficient=args.min_coefficient,
        model=args.model,
        max_searches=args.max_searches,
    )
    print(json.dumps(stats.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
