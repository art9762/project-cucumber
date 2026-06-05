"""Хеширование паролей через argon2 (argon2-cffi).

Пароли НИКОГДА не хранятся в открытом виде — только argon2-хеш в users.password_hash.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Вернуть argon2-хеш пароля (с солью и параметрами внутри строки)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True, если пароль соответствует хешу. Любая ошибка проверки → False."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
