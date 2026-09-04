"""secure server-side SMART token custody

Revision ID: 0005_secure_smart_tokens
Revises: 0004_durable_ehr_outbox
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_secure_smart_tokens"
down_revision = "0004_durable_ehr_outbox"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "smart_authorization_states",
        sa.Column("state_key", sa.String(), primary_key=True),
        sa.Column("encrypted_transaction", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_smart_authorization_states_expires_at", "smart_authorization_states", ["expires_at"])
    op.create_table(
        "smart_tokens",
        sa.Column("tenant_id", sa.String(), primary_key=True),
        sa.Column("clinician_id", sa.String(), primary_key=True),
        sa.Column("encrypted_token", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.Float(), nullable=False),
        sa.Column("practitioner_id", sa.String(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("smart_tokens")
    op.drop_table("smart_authorization_states")