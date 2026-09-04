"""create the initial durable clinic record schema

Revision ID: 0001_durable_clinic_records
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_durable_clinic_records"
down_revision = None
branch_labels = None
depends_on = None


def _create_if_missing(name, *columns, indexes=()):
    if name in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(name, *columns)
    for index_name, index_columns in indexes:
        op.create_index(index_name, name, index_columns, unique=False)


def upgrade():
    # This revision doubles as a safe baseline for installations that used the
    # former Base.metadata.create_all startup path: existing tables are retained,
    # while missing durable tables are created.
    _create_if_missing(
        "encounters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("clinician_id", sa.String(), nullable=True),
        sa.Column("patient_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("transcription_job_ids", sa.String(), nullable=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_if_missing(
        "clinical_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("encounter_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("last_edited_by", sa.String(), nullable=True),
        sa.Column("is_finalized", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("subjective", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("assessment", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_clinical_notes_encounter_id", ["encounter_id"]),),
    )
    _create_if_missing(
        "transcription_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("audio_url", sa.String(), nullable=False),
        sa.Column("language_code", sa.String(), nullable=True),
        sa.Column("target_language", sa.String(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_if_missing(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subject", "tenant_id", name="uq_users_subject_tenant"),
    )
    _create_if_missing(
        "audio_blobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        indexes=(("ix_audio_blobs_tenant_id", ["tenant_id"]),),
    )


def downgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in ("audio_blobs", "users", "transcription_jobs", "clinical_notes", "encounters"):
        if table in existing:
            op.drop_table(table)