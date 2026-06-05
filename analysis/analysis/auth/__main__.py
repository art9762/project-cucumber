"""CLI для сидинга учётных записей (Фаза 6).

    python -m analysis.auth create-admin  --username X --password Y
    python -m analysis.auth create-user   --username X --password Y [--role viewer]

Пишет в свою таблицу users реальной analysis-БД (DSN из env/.env).
Ошибка, если username уже существует. Пароль хешируется argon2 — НЕ хранится в открытую.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from analysis.auth.hashing import hash_password
from analysis.storage.db import get_analysis_sessionmaker
from analysis.storage.orm import UserORM


async def _create_user(username: str, password: str, role: str) -> int:
    sessionmaker = get_analysis_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.execute(
            select(UserORM).where(UserORM.username == username)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"error: user '{username}' already exists", file=sys.stderr)
            return 1
        session.add(
            UserORM(
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
        )
        await session.commit()
    print(f"created user '{username}' with role '{role}'")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m analysis.auth")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="создать пользователя с ролью admin")
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--password", required=True)

    p_user = sub.add_parser("create-user", help="создать пользователя с заданной ролью")
    p_user.add_argument("--username", required=True)
    p_user.add_argument("--password", required=True)
    p_user.add_argument("--role", default="viewer", choices=["admin", "viewer"])

    args = parser.parse_args(argv)

    if args.command == "create-admin":
        role = "admin"
    else:
        role = args.role

    return asyncio.run(_create_user(args.username, args.password, role))


if __name__ == "__main__":
    raise SystemExit(main())
