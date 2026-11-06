"""Save threshold assessments, risk episodes and caregiver acknowledgements."""

from alembic import op

revision = "0003_explained_alerts"
down_revision = "0002_monitoring"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE assessments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid NOT NULL REFERENCES patients,
            reading_id uuid NOT NULL UNIQUE REFERENCES readings,
            scope text NOT NULL CHECK (scope IN ('current', 'historical')),
            concern text CHECK (concern IN ('none', 'watch', 'high')),
            data_quality text NOT NULL CHECK (data_quality IN ('fresh', 'incomplete')),
            findings jsonb NOT NULL,
            rule_version text NOT NULL,
            evaluated_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("ALTER TABLE patients ADD current_assessment_id uuid REFERENCES assessments")
    op.execute("""
        CREATE TABLE alerts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id uuid NOT NULL REFERENCES patients,
            kind text NOT NULL CHECK (kind = 'risk'),
            status text NOT NULL CHECK (status IN ('open', 'acknowledged')),
            peak_priority text NOT NULL CHECK (peak_priority IN ('watch', 'high')),
            assignee_id uuid NOT NULL REFERENCES caregivers,
            original_assessment_id uuid NOT NULL REFERENCES assessments,
            latest_assessment_id uuid NOT NULL REFERENCES assessments,
            opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            acknowledged_at timestamptz,
            acknowledged_by uuid REFERENCES caregivers,
            revision bigint NOT NULL DEFAULT 1,
            CHECK ((status = 'acknowledged') = (acknowledged_at IS NOT NULL)),
            CHECK ((status = 'acknowledged') = (acknowledged_by IS NOT NULL))
        )
    """)
    op.execute("""CREATE UNIQUE INDEX active_episode ON alerts (patient_id, kind)
                  WHERE status IN ('open', 'acknowledged')""")
    op.execute("""
        CREATE TABLE alert_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_id uuid NOT NULL REFERENCES alerts,
            event_type text NOT NULL CHECK (event_type IN ('opened', 'updated', 'acknowledged')),
            assessment_id uuid REFERENCES assessments,
            caregiver_id uuid REFERENCES caregivers,
            command_id uuid UNIQUE,
            occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("CREATE INDEX episode_history ON alert_events (alert_id, occurred_at, id)")


def downgrade() -> None:
    op.drop_table("alert_events")
    op.drop_table("alerts")
    op.execute("ALTER TABLE patients DROP COLUMN current_assessment_id")
    op.drop_table("assessments")
