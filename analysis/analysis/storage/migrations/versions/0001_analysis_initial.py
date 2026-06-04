"""initial schema: analysis_runs, categories, item_analysis

Revision ID: 0001_analysis_initial
Revises:
Create Date: 2026-06-04
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_analysis_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')  # gen_random_uuid()

    op.create_table(
        "analysis_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("cursor", sa.Text()),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
    )

    op.create_table(
        "categories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])

    op.create_table(
        "item_analysis",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("scores", postgresql.JSONB(), nullable=True),
        sa.Column("coefficient", sa.Float(), nullable=True),
        sa.Column("tier", sa.String(length=1), nullable=True),
        sa.Column(
            "analyzed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("model_used", sa.Text(), nullable=True),
        sa.UniqueConstraint("item_id", name="uq_item_analysis_item_id"),
    )
    op.create_index("ix_item_analysis_item_id", "item_analysis", ["item_id"])
    op.create_index("ix_item_analysis_category_id", "item_analysis", ["category_id"])

    # Seed top-level categories
    categories_table = sa.table(
        "categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("parent_id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.Text()),
        sa.column("title", sa.Text()),
        sa.column("approved", sa.Boolean()),
    )
    op.bulk_insert(
        categories_table,
        [
            {"id": uuid.uuid4(), "parent_id": None, "slug": "ai", "title": "AI", "approved": True},
            {"id": uuid.uuid4(), "parent_id": None, "slug": "engineering", "title": "Инженерия", "approved": True},
            {"id": uuid.uuid4(), "parent_id": None, "slug": "product", "title": "Продукт", "approved": True},
            {"id": uuid.uuid4(), "parent_id": None, "slug": "science", "title": "Наука", "approved": True},
            {"id": uuid.uuid4(), "parent_id": None, "slug": "tools", "title": "Инструменты", "approved": True},
            {"id": uuid.uuid4(), "parent_id": None, "slug": "other", "title": "Прочее", "approved": True},
        ],
    )


def downgrade() -> None:
    op.drop_table("item_analysis")
    op.drop_table("categories")
    op.drop_table("analysis_runs")
