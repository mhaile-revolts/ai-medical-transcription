"""Add durable idempotency claims for mobile audio uploads.

Revision ID: 0007_audio_upload_idempotency
Revises: 0006_ehr_delivery_leases
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_audio_upload_idempotency"
down_revision = "0006_ehr_delivery_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_upload_idempotency",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("clinician_id", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.String(length=128), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "clinician_id", "encounter_id", "capture_id",
                            name="uq_audio_upload_idempotency_capture"),
    )


def downgrade() -> None:
    op.drop_table("audio_upload_idempotency")