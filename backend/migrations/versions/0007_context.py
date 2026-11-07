"""Store structured observations and immutable contextual assessments."""
from alembic import op

revision = "0007_context"
down_revision = "0006_data_quality"


def upgrade() -> None:
    op.execute("""CREATE TABLE observations (
        id uuid PRIMARY KEY,
        patient_id uuid NOT NULL REFERENCES patients,
        caregiver_id uuid NOT NULL REFERENCES caregivers,
        tag text NOT NULL CHECK (tag IN ('breathlessness','dizziness','reduced_intake')),
        present boolean NOT NULL,
        note text CHECK (length(note)<=500),
        created_at timestamptz NOT NULL,
        expires_at timestamptz NOT NULL CHECK (expires_at=created_at+interval '10 minutes'),
        ordinal bigint GENERATED ALWAYS AS IDENTITY UNIQUE
    )""")
    op.execute("CREATE INDEX observation_latest ON observations (patient_id,tag,created_at DESC,ordinal DESC)")
    op.execute("""ALTER TABLE assessments
        DROP CONSTRAINT assessments_reading_id_key,
        ALTER reading_id DROP NOT NULL,
        DROP CONSTRAINT assessments_data_quality_check,
        ADD CHECK (data_quality IN ('fresh','incomplete','stale','unavailable')),
        ADD observation_id uuid REFERENCES observations,
        ADD trigger_kind text NOT NULL DEFAULT 'reading'
            CHECK (trigger_kind IN ('reading','observation','observation_expiry')),
        ADD trend_summary jsonb NOT NULL DEFAULT '[]',
        ADD CHECK (trigger_kind<>'reading' OR reading_id IS NOT NULL),
        ADD CHECK ((trigger_kind='observation') = (observation_id IS NOT NULL))""")
    op.execute("CREATE UNIQUE INDEX reading_assessment ON assessments (reading_id) WHERE trigger_kind='reading'")
    op.execute("CREATE UNIQUE INDEX observation_assessment ON assessments (observation_id) WHERE observation_id IS NOT NULL")
    op.execute("ALTER TABLE patients ADD context_expires_at timestamptz")


def downgrade() -> None:
    # Refuse to erase contextual evidence during a downgrade.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM observations) OR EXISTS (
            SELECT 1 FROM assessments WHERE trigger_kind<>'reading' OR trend_summary<>'[]'::jsonb)
        THEN RAISE EXCEPTION 'Context evidence exists; downgrade would lose M4 data'; END IF;
    END $$""")
    op.execute("ALTER TABLE patients DROP context_expires_at")
    op.execute("DROP INDEX observation_assessment")
    op.execute("DROP INDEX reading_assessment")
    op.execute("""ALTER TABLE assessments DROP COLUMN observation_id, DROP COLUMN trigger_kind,
        DROP COLUMN trend_summary, ALTER reading_id SET NOT NULL,
        ADD UNIQUE (reading_id), DROP CONSTRAINT assessments_data_quality_check,
        ADD CHECK (data_quality IN ('fresh','incomplete'))""")
    op.drop_table("observations")
