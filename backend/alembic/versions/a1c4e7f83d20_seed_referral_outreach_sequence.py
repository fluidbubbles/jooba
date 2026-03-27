"""seed referral outreach, clarification, and thank-you sequences

Revision ID: a1c4e7f83d20
Revises: 2fd7137c1f5a
Create Date: 2026-03-26
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision: str = "a1c4e7f83d20"
down_revision: str | Sequence[str] | None = "2fd7137c1f5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEQUENCE_NAME = "Referral Outreach"
SEQUENCE_ID = uuid.UUID("00000000-0000-4000-a000-000000000001")
STEP_ID = uuid.UUID("00000000-0000-4000-a000-000000000002")

CLARIFICATION_NAME = "Referral Clarification"
CLARIFICATION_ID = uuid.UUID("00000000-0000-4000-a000-000000000003")
CLARIFICATION_STEP_ID = uuid.UUID("00000000-0000-4000-a000-000000000004")

THANK_YOU_NAME = "Referral Thank You"
THANK_YOU_ID = uuid.UUID("00000000-0000-4000-a000-000000000005")
THANK_YOU_STEP_ID = uuid.UUID("00000000-0000-4000-a000-000000000006")


def upgrade() -> None:
    now = datetime.now(timezone.utc)

    sequences = sa.table(
        "sequences",
        sa.column("id", sa.Uuid),
        sa.column("name", sa.String),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    steps = sa.table(
        "sequence_steps",
        sa.column("id", sa.Uuid),
        sa.column("sequence_id", sa.Uuid),
        sa.column("step_order", sa.Integer),
        sa.column("subject", sa.String),
        sa.column("body_html", sa.Text),
        sa.column("delay_minutes", sa.Integer),
    )

    op.execute(
        sequences.insert().values(
            id=SEQUENCE_ID,
            name=SEQUENCE_NAME,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    op.execute(
        steps.insert().values(
            id=STEP_ID,
            sequence_id=SEQUENCE_ID,
            step_order=0,
            subject="{{first_name}}, a colleague suggested we connect",
            body_html=(
                "<p>Hi {{first_name}},</p>"
                "<p>A colleague of yours suggested I reach out to you about "
                "an opportunity that might be a great fit.</p>"
                "<p>I'd love to tell you more — would you have a few minutes "
                "for a quick chat this week?</p>"
            ),
            delay_minutes=0,
        )
    )

    # Clarification sequence — sent to referrer when email is missing
    op.execute(
        sequences.insert().values(
            id=CLARIFICATION_ID,
            name=CLARIFICATION_NAME,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    op.execute(
        steps.insert().values(
            id=CLARIFICATION_STEP_ID,
            sequence_id=CLARIFICATION_ID,
            step_order=0,
            subject="Re: Quick follow-up — contact details for your referral",
            body_html=(
                "<p>Hi {{first_name}},</p>"
                "<p>Thanks for the referral! Could you share their email address "
                "so I can reach out directly?</p>"
                "<p>Appreciate the help!</p>"
            ),
            delay_minutes=0,
        )
    )


    # Thank-you sequence — sent to referrer when referral has valid email
    op.execute(
        sequences.insert().values(
            id=THANK_YOU_ID,
            name=THANK_YOU_NAME,
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    op.execute(
        steps.insert().values(
            id=THANK_YOU_STEP_ID,
            sequence_id=THANK_YOU_ID,
            step_order=0,
            subject="Re: Thanks for the referral, {{first_name}}!",
            body_html=(
                "<p>Hi {{first_name}},</p>"
                "<p>Just wanted to say thanks for pointing me in the right direction — "
                "I really appreciate it! I'll be reaching out to them shortly.</p>"
                "<p>If you think of anyone else who might be a fit, I'd love to hear about it.</p>"
            ),
            delay_minutes=0,
        )
    )


def downgrade() -> None:
    for sid in (SEQUENCE_ID, CLARIFICATION_ID, THANK_YOU_ID):
        op.execute(
            sa.text("DELETE FROM sequence_steps WHERE sequence_id = :sid"),
            {"sid": sid},
        )
        op.execute(
            sa.text("DELETE FROM sequences WHERE id = :sid"),
            {"sid": sid},
        )
