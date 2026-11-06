"""Persist response deadlines and caregiver handoffs."""
from alembic import op

revision = "0005_escalation"
down_revision = "0004_rename_patient"


def upgrade() -> None:
    op.execute("ALTER TABLE alerts ADD escalation_due_at timestamptz")
    op.execute("""UPDATE alerts SET escalation_due_at = opened_at +
        CASE WHEN peak_priority='high' THEN interval '30 seconds' ELSE interval '60 seconds' END
        WHERE status='open'""")
    op.execute("ALTER TABLE alert_events DROP CONSTRAINT alert_events_event_type_check")
    op.execute("""ALTER TABLE alert_events ADD CHECK
        (event_type IN ('opened','updated','acknowledged','escalated','reopened'))""")


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP COLUMN escalation_due_at")
    op.execute("ALTER TABLE alert_events DROP CONSTRAINT alert_events_event_type_check")
    op.execute("UPDATE alert_events SET event_type='updated' WHERE event_type IN ('escalated','reopened')")
    op.execute("ALTER TABLE alert_events ADD CHECK (event_type IN ('opened','updated','acknowledged'))")
