"""email_events composite index for unreplied detection

Revision ID: f8e3a91c2b04
Revises: b65bf38f5422
Create Date: 2026-03-25

See docs/architecture/architecture.md §7 (email_events index).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f8e3a91c2b04"
down_revision: Union[str, Sequence[str], None] = "b65bf38f5422"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_email_events_enrollment_direction_sentiment_created",
        "email_events",
        ["enrollment_id", "direction", "sentiment", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_events_enrollment_direction_sentiment_created",
        table_name="email_events",
    )
