"""persist conversation sessions

Revision ID: 0002_durable_conversation_sessions
Revises: 0001_durable_clinic_records
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_durable_conversation_sessions"
down_revision = "0001_durable_clinic_records"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if "encounters" in tables:
        encounter_columns = {column["name"] for column in inspector.get_columns("encounters")}
        if "assigned_scribe_id" not in encounter_columns:
            op.add_column(
                "encounters",
                sa.Column("assigned_scribe_id", sa.String(), nullable=True),
            )
    if "conversation_sessions" not in tables:
        op.create_table(
            "conversation_sessions",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("title", sa.String(), nullable=True),
            sa.Column("transcription_job_ids", sa.Text(), nullable=True),
            sa.Column("tenant_id", sa.String(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_conversation_sessions_tenant_id",
            "conversation_sessions",
            ["tenant_id"],
            unique=False,
        )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    if "conversation_sessions" in inspector.get_table_names():
        op.drop_index("ix_conversation_sessions_tenant_id", table_name="conversation_sessions")
        op.drop_table("conversation_sessions")
    if "encounters" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("encounters")}
        if "assigned_scribe_id" in columns:
            op.drop_column("encounters", "assigned_scribe_id")