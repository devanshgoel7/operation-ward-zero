"""Complete caregiver lifecycle without discarding existing evidence."""
from alembic import op

revision = "0008_resolution"
down_revision = "0007_context"


def upgrade() -> None:
    op.execute("""ALTER TABLE alerts
        ADD response_started_at timestamptz,
        ADD escalated_at timestamptz,
        ADD resolved_by uuid REFERENCES caregivers,
        ADD recovery_count integer NOT NULL DEFAULT 0 CHECK (recovery_count BETWEEN 0 AND 3),
        ADD recovery_observed_at timestamptz""")
    op.execute("""UPDATE alerts a SET response_started_at=coalesce(
        (SELECT max(occurred_at) FROM alert_events WHERE alert_id=a.id AND event_type='reopened'),opened_at)""")
    op.execute("""UPDATE alerts a SET escalated_at=(SELECT max(occurred_at) FROM alert_events
        WHERE alert_id=a.id AND event_type='escalated' AND occurred_at>=a.response_started_at)""")
    op.execute("ALTER TABLE alerts ALTER response_started_at SET NOT NULL")
    op.execute("ALTER TABLE alerts ALTER response_started_at SET DEFAULT clock_timestamp()")
    op.execute("ALTER TABLE alert_events ADD details jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("CREATE INDEX due_alerts ON alerts (escalation_due_at) WHERE status='open'")
    op.execute("CREATE INDEX caregiver_inbox ON alerts (assignee_id,status,opened_at DESC)")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM alert_events WHERE details<>'{}'::jsonb) THEN
            RAISE EXCEPTION 'Cannot discard saved M5 lifecycle details';
        END IF;
    END $$""")
    op.drop_index("caregiver_inbox")
    op.drop_index("due_alerts")
    op.execute("ALTER TABLE alert_events DROP details")
    op.execute("""ALTER TABLE alerts DROP response_started_at, DROP escalated_at,
        DROP resolved_by, DROP recovery_count, DROP recovery_observed_at""")
