"""Use role labels for the existing demo caregiver identities."""
from alembic import op

revision = "0009_caregiver_labels"
down_revision = "0008_resolution"


def upgrade() -> None:
    op.execute("""UPDATE caregivers SET display_name = labels.name
        FROM (VALUES ('10000000-0000-0000-0000-000000000001'::uuid, 'Primary caregiver'),
                     ('10000000-0000-0000-0000-000000000002'::uuid, 'Backup caregiver')) AS labels(id, name)
        WHERE caregivers.id = labels.id""")


def downgrade() -> None:
    op.execute("""UPDATE caregivers SET display_name = labels.name
        FROM (VALUES ('10000000-0000-0000-0000-000000000001'::uuid, 'Alex Morgan'),
                     ('10000000-0000-0000-0000-000000000002'::uuid, 'Sam Rivera')) AS labels(id, name)
        WHERE caregivers.id = labels.id""")
