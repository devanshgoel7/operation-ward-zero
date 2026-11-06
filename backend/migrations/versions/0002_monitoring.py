"""Store synthetic patients, registered devices and their readings."""

from alembic import op

revision = "0002_monitoring"
down_revision = "0001_environment"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE caregivers (id uuid PRIMARY KEY, display_name text NOT NULL)
    """)
    op.execute("""
        CREATE TABLE patients (
            id uuid PRIMARY KEY,
            display_name text NOT NULL,
            primary_caregiver_id uuid NOT NULL REFERENCES caregivers,
            backup_caregiver_id uuid NOT NULL REFERENCES caregivers,
            latest_reading_id uuid,
            monitoring_started_at timestamptz NOT NULL DEFAULT now(),
            CHECK (primary_caregiver_id <> backup_caregiver_id)
        )
    """)
    op.execute("""
        CREATE TABLE devices (
            id uuid PRIMARY KEY,
            patient_id uuid NOT NULL UNIQUE REFERENCES patients,
            label text NOT NULL,
            UNIQUE (id, patient_id)
        )
    """)
    op.execute("""
        CREATE TABLE readings (
            id uuid PRIMARY KEY,
            device_id uuid NOT NULL,
            patient_id uuid NOT NULL REFERENCES patients,
            sequence bigint NOT NULL CHECK (sequence >= 1),
            observed_at timestamptz NOT NULL,
            received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            heart_rate_bpm double precision CHECK (heart_rate_bpm > 0),
            spo2_pct double precision CHECK (spo2_pct BETWEEN 0 AND 100),
            systolic_mmhg double precision CHECK (systolic_mmhg > 0),
            diastolic_mmhg double precision CHECK (diastolic_mmhg > 0),
            temperature_c double precision,
            payload_hash text NOT NULL,
            CHECK (systolic_mmhg >= diastolic_mmhg),
            FOREIGN KEY (device_id, patient_id) REFERENCES devices (id, patient_id),
            UNIQUE (device_id, sequence)
        )
    """)
    op.execute("ALTER TABLE patients ADD FOREIGN KEY (latest_reading_id) REFERENCES readings")
    op.execute("CREATE INDEX reading_history ON readings (patient_id, observed_at DESC, id DESC)")
    op.execute("""
        INSERT INTO caregivers VALUES
        ('10000000-0000-0000-0000-000000000001', 'Alex Morgan'),
        ('10000000-0000-0000-0000-000000000002', 'Sam Rivera')
    """)
    op.execute("""
        INSERT INTO patients (id, display_name, primary_caregiver_id, backup_caregiver_id)
        SELECT id::uuid, name, '10000000-0000-0000-0000-000000000001'::uuid,
                               '10000000-0000-0000-0000-000000000002'::uuid
        FROM (VALUES
            ('20000000-0000-0000-0000-000000000001', 'Mira Shah'),
            ('20000000-0000-0000-0000-000000000002', 'Jon Ellis'),
            ('20000000-0000-0000-0000-000000000003', 'Lena Park')
        ) AS fixtures(id, name)
    """)
    op.execute("""
        INSERT INTO devices SELECT ('3' || substr(id::text, 2))::uuid, id, 'Home monitor'
        FROM patients
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE patients DROP COLUMN latest_reading_id")
    for table in ("readings", "devices", "patients", "caregivers"):
        op.drop_table(table)
