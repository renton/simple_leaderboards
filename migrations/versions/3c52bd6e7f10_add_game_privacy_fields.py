"""add game privacy fields

Adds per-game privacy-policy fields backing the public /privacy/<slug> page:
operator_name, contact_email, privacy_policy_extra (free-form extra clauses),
and privacy_updated_at (last time the policy/game was edited).

Revision ID: 3c52bd6e7f10
Revises: 2b41ac9d5e3a
Create Date: 2026-06-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "3c52bd6e7f10"
down_revision = "2b41ac9d5e3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("games", sa.Column("operator_name", sa.String(length=128), nullable=True))
    op.add_column("games", sa.Column("contact_email", sa.String(length=254), nullable=True))
    op.add_column("games", sa.Column("privacy_policy_extra", sa.Text(), nullable=True))
    op.add_column(
        "games",
        sa.Column("privacy_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("games", "privacy_updated_at")
    op.drop_column("games", "privacy_policy_extra")
    op.drop_column("games", "contact_email")
    op.drop_column("games", "operator_name")
