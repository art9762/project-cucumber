"""add source_schedules table

Revision ID: 0002_source_schedules
Revises: 0001_initial
Create Date: 2026-06-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_source_schedules"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_schedules",
        sa.Column("source", sa.Text(), primary_key=True),
        sa.Column("cron", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("source_schedules")
