"""add webhook_secret to nylas_accounts

Revision ID: bed91f28dd58
Revises: a1c4e7f83d20
Create Date: 2026-03-26 20:43:05.760401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bed91f28dd58'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7f83d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('nylas_accounts', sa.Column('webhook_secret', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('nylas_accounts', 'webhook_secret')
