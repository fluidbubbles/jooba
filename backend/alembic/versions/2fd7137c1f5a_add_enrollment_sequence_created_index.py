"""add enrollment sequence/created/id composite index

Revision ID: 2fd7137c1f5a
Revises: 48e13ba09f3d
Create Date: 2026-03-26
"""

from collections.abc import Sequence

from alembic import op


revision: str = "2fd7137c1f5a"
down_revision: str | Sequence[str] | None = "48e13ba09f3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_enrollments_sequence_created_id",
        "enrollments",
        ["sequence_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_enrollments_sequence_created_id", table_name="enrollments")
