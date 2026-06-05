"""research + embeddings: item_research, item_embeddings (+ pgvector)

Revision ID: 0002_research_embeddings
Revises: 0001_analysis_initial
Create Date: 2026-06-05
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_research_embeddings"
down_revision: str | None = "0001_analysis_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Размерность эмбеддинга (fastembed BAAI/bge-small-en-v1.5). Должна совпадать с
# analysis.storage.orm.EMBEDDING_DIM.
EMBEDDING_DIM = 384


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')  # pgvector

    op.create_table(
        "item_research",
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
        sa.Column("summary", sa.Text()),
        sa.Column("competitors", postgresql.JSONB()),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("maturity_signal", sa.Float()),
        sa.Column("potential_signal", sa.Float()),
        sa.Column("model_used", sa.Text()),
        sa.Column(
            "researched_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("item_id", name="uq_item_research_item_id"),
    )
    op.create_index("ix_item_research_item_id", "item_research", ["item_id"])

    op.create_table(
        "item_embeddings",
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
        sa.Column("embedding", _vector_column_type()),
        sa.Column("model", sa.Text()),
        sa.Column("dim", sa.Integer()),
        sa.Column(
            "embedded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("item_id", name="uq_item_embeddings_item_id"),
    )
    op.create_index("ix_item_embeddings_item_id", "item_embeddings", ["item_id"])

    # ANN-индекс для косинусной близости (оператор <=>). IVFFlat требует данных
    # для обучения списков; на свежей таблице ок — добавляем сразу, lists=100.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_item_embeddings_vec "
        "ON item_embeddings USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )


def _vector_column_type():
    """Тип колонки вектора: pgvector.Vector если доступен, иначе текстовый фолбэк."""
    from pgvector.sqlalchemy import Vector

    return Vector(EMBEDDING_DIM)


def downgrade() -> None:
    op.drop_table("item_embeddings")
    op.drop_table("item_research")
