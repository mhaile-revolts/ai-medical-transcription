"""durable EHR connection and write-back outbox

Revision ID: 0004_durable_ehr_outbox
Revises: 0003_smart_encounter_confirmation
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_durable_ehr_outbox"
down_revision = "0003_smart_encounter_confirmation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ehr_connections",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False), sa.Column("base_url", sa.String()),
        sa.Column("auth_type", sa.String(), nullable=False), sa.Column("auth_config", sa.JSON(), nullable=False),
        sa.Column("supported_capabilities", sa.JSON(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ehr_connections_tenant_id", "ehr_connections", ["tenant_id"])
    op.create_table(
        "ehr_messages",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False), sa.Column("resource_type", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False), sa.Column("direction", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("last_error", sa.Text()),
        sa.Column("idempotency_key", sa.String(), nullable=False), sa.Column("remote_resource_id", sa.String()),
        sa.Column("related_encounter_id", sa.Uuid()), sa.Column("related_note_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True)), sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)), sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "connection_id", "idempotency_key", name="uq_ehr_message_idempotency"),
    )
    op.create_index("ix_ehr_messages_tenant_id", "ehr_messages", ["tenant_id"])


def downgrade():
    op.drop_table("ehr_messages")
    op.drop_table("ehr_connections")