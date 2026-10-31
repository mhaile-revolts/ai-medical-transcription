"""Store the detected language confidence on transcription jobs.

Revision ID: 0008_transcription_language_confidence
Revises: 0007_audio_upload_idempotency
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_transcription_language_confidence"
down_revision = "0007_audio_upload_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transcription_jobs",
        sa.Column("language_probability", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcription_jobs", "language_probability")
