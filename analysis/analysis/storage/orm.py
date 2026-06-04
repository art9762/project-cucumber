"""SQLAlchemy ORM.

Два независимых metadata:

- ``Base`` — СВОИ таблицы анализа (``analysis_runs``, ``categories``,
  ``item_analysis``). Только их видит Alembic-история анализа.
- ``ReadBase`` — read-only маппинг таблицы движка ``items``. НЕ входит в
  миграции анализа: движок владеет этой таблицей, мы только читаем.

Решение 1а: общая Postgres, к таблицам движка относимся как к read-only
внешнему контракту — не импортируем ORM движка, держим свой минимальный маппинг.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class _ArrayOfText(TypeDecorator):
    """ARRAY(Text) на Postgres, JSON-список на SQLite (для unit-тестов)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Text))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        return value

    def process_result_value(self, value, dialect):
        return value if value is not None else []


class _JSONB(TypeDecorator):
    """JSONB на Postgres, JSON на SQLite (для unit-тестов)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class _TZ(TypeDecorator):
    """TIMESTAMP(timezone=True) на Postgres, DateTime на SQLite (для unit-тестов)."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TIMESTAMP(timezone=True))
        return dialect.type_descriptor(DateTime(timezone=True))


class Base(DeclarativeBase):
    """Metadata СВОИХ таблиц анализа (цель Alembic-истории анализа)."""


class ReadBase(DeclarativeBase):
    """Metadata read-only маппинга таблиц движка. Вне миграций анализа."""


# --------------------------------------------------------------------------
# Read-only маппинг таблицы движка `items` (только нужные колонки).
# Не писать сюда; владелец схемы — движок.
# --------------------------------------------------------------------------
class ItemReadORM(ReadBase):
    __tablename__ = "items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(_ArrayOfText, nullable=False, server_default="{}")
    created_at: Mapped[datetime | None] = mapped_column(_TZ)
    fetched_at: Mapped[datetime | None] = mapped_column(_TZ)


# --------------------------------------------------------------------------
# Свои таблицы анализа.
# --------------------------------------------------------------------------
class AnalysisRunORM(Base):
    """Прогон анализа (аналог `jobs` у движка) — для инкрементальности и наблюдаемости."""

    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # classify / score / ...
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    cursor: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(_JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(_TZ)
    finished_at: Mapped[datetime | None] = mapped_column(_TZ)


class CategoryORM(Base):
    """Узел дерева категорий (гибридная таксономия: seed + предложенные моделью)."""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("slug", name="uq_categories_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE")
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    approved: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    created_at: Mapped[datetime | None] = mapped_column(
        _TZ, server_default=text("now()")
    )

    children: Mapped[list["CategoryORM"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    parent: Mapped["CategoryORM | None"] = relationship(
        back_populates="children", remote_side="CategoryORM.id"
    )


class ItemAnalysisORM(Base):
    """Результат анализа одного item (1:1 к items.id). Колонки фаз 1–2 — nullable-задел."""

    __tablename__ = "item_analysis"
    __table_args__ = (UniqueConstraint("item_id", name="uq_item_analysis_item_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # FK на таблицу движка items (другой metadata — ссылаемся через объект колонки).
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(ItemReadORM.__table__.c.id, ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(  # Фаза 1
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL")
    )
    scores: Mapped[dict | None] = mapped_column(_JSONB)  # Фаза 2
    coefficient: Mapped[float | None] = mapped_column(Float)  # Фаза 2
    tier: Mapped[str | None] = mapped_column(String(1))  # Фаза 2: S/A/B/C/D
    analyzed_at: Mapped[datetime | None] = mapped_column(
        _TZ, server_default=text("now()")
    )
    model_used: Mapped[str | None] = mapped_column(Text)
