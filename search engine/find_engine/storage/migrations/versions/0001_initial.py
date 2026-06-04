"""initial schema: items, raw_records, jobs

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-04
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')  # gen_random_uuid()

    op.create_table(
        "items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("author", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("score", sa.Integer()),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("source", "external_id", name="uq_items_source_external_id"),
    )
    op.create_index("ix_items_source", "items", ["source"])
    op.create_index("ix_items_created_at", "items", ["created_at"])

    op.create_table(
        "raw_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_raw_records_item_id", "raw_records", ["item_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("since", sa.TIMESTAMP(timezone=True)),
        sa.Column("cursor", sa.Text()),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_jobs_source_status", "jobs", ["source", "status"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("raw_records")
    op.drop_table("items")
