"""Add durable EHR outbox delivery leases.

Revision ID: 0006_ehr_delivery_leases
Revises: 0005_secure_smart_tokens
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_ehr_delivery_leases"
down_revision = "0005_secure_smart_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ehr_messages", sa.Column("claimed_by", sa.String(), nullable=True))
    op.add_column("ehr_messages", sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ehr_messages_claim_expires_at", "ehr_messages", ["claim_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ehr_messages_claim_expires_at", table_name="ehr_messages")
    op.drop_column("ehr_messages", "claim_expires_at")
    op.drop_column("ehr_messages", "claimed_by")