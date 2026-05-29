"""add champions partial index

Partial composite index supporting GET /api/v1/champions. Covers the common
filter (game_id, optional submitted_at window) restricted to seeded, non-deleted
rows so the index is small.

Revision ID: 2b41ac9d5e3a
Revises: 1ba0a7567b1f
Create Date: 2026-05-29
"""

from __future__ import annotations

from alembic import op


revision = "2b41ac9d5e3a"
down_revision = "1ba0a7567b1f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_scores_champions",
        "scores",
        ["game_id", "submitted_at", "seed"],
        postgresql_where="seed IS NOT NULL AND deleted_at IS NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_scores_champions", table_name="scores")
