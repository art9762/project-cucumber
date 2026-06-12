"""SQLAlchemy ORM-таблицы: items, raw_records, jobs, source_schedules."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ItemORM(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_items_source_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    raw_records: Mapped[list["RawRecordORM"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class RawRecordORM(Base):
    __tablename__ = "raw_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    item: Mapped[ItemORM | None] = relationship(back_populates="raw_records")


class JobORM(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    since: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    cursor: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class SourceScheduleORM(Base):
    __tablename__ = "source_schedules"

    source: Mapped[str] = mapped_column(Text, primary_key=True)
    cron: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
