"""persist externally confirmed SMART encounters and consent evidence"""

from alembic import op
import sqlalchemy as sa

revision = "0003_smart_encounter_confirmation"
down_revision = "0002_durable_conversation_sessions"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("encounters")}
    additions = [
        ("external_patient_id", sa.String()),
        ("external_encounter_id", sa.String()),
        ("external_encounter_status", sa.String()),
        ("consent_obtained_at", sa.DateTime(timezone=True)),
        ("consent_method", sa.String()),
        ("consent_version", sa.String()),
        ("consent_revoked_at", sa.DateTime(timezone=True)),
    ]
    for name, type_ in additions:
        if name not in columns:
            op.add_column("encounters", sa.Column(name, type_, nullable=True))


def downgrade():
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("encounters")}
    for name in ("consent_revoked_at", "consent_version", "consent_method", "consent_obtained_at",
                 "external_encounter_status", "external_encounter_id", "external_patient_id"):
        if name in columns:
            op.drop_column("encounters", name)