"""Persist freshness watermarks, gap recovery and delayed-review episodes."""
from alembic import op

revision = "0006_data_quality"
down_revision = "0005_escalation"


def upgrade() -> None:
    op.execute("""ALTER TABLE patients
        ADD last_complete_at timestamptz,
        ADD last_known_assessment_id uuid REFERENCES assessments,
        ADD gap_recovery_count integer NOT NULL DEFAULT 0 CHECK (gap_recovery_count BETWEEN 0 AND 2)""")
    op.execute("""UPDATE patients p SET last_complete_at = (
        SELECT max(observed_at) FROM readings WHERE patient_id=p.id AND
        num_nonnulls(heart_rate_bpm, spo2_pct, systolic_mmhg, diastolic_mmhg, temperature_c)=5),
        last_known_assessment_id = (SELECT a.id FROM assessments a JOIN readings r ON r.id=a.reading_id
        WHERE a.patient_id=p.id AND scope='current' AND concern IS NOT NULL
        ORDER BY r.observed_at DESC, r.id DESC LIMIT 1)""")
    op.execute("""ALTER TABLE alerts
        DROP CONSTRAINT alerts_kind_check, DROP CONSTRAINT alerts_status_check,
        DROP CONSTRAINT alerts_check, DROP CONSTRAINT alerts_check1,
        ALTER original_assessment_id DROP NOT NULL, ALTER latest_assessment_id DROP NOT NULL,
        ADD resolved_at timestamptz,
        ADD CHECK (kind IN ('risk','monitoring_gap','delayed_review')),
        ADD CHECK (status IN ('open','acknowledged','resolved')),
        ADD CHECK ((status='resolved') = (resolved_at IS NOT NULL)),
        ADD CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL)),
        ADD CHECK (status='resolved' OR ((status='acknowledged') = (acknowledged_at IS NOT NULL))),
        ADD CHECK (kind='monitoring_gap' OR
            (original_assessment_id IS NOT NULL AND latest_assessment_id IS NOT NULL))""")
    op.execute("""ALTER TABLE alert_events DROP CONSTRAINT alert_events_event_type_check,
        ADD CHECK (event_type IN ('opened','updated','acknowledged','reopened','escalated','resolved'))""")

    # Surface M2 historical findings once, without changing their immutable assessments.
    op.execute("""WITH evidence AS (
        SELECT patient_id, array_agg(id ORDER BY evaluated_at,id) AS ids,
               bool_or(concern='high') AS high
        FROM assessments WHERE scope='historical' AND concern IN ('watch','high') GROUP BY patient_id
    ), episodes AS (
        INSERT INTO alerts (patient_id,kind,status,peak_priority,assignee_id,original_assessment_id,
                            latest_assessment_id,escalation_due_at,revision)
        SELECT p.id,'delayed_review','open',CASE WHEN e.high THEN 'high' ELSE 'watch' END,
               p.primary_caregiver_id,e.ids[1],e.ids[cardinality(e.ids)],
               now()+CASE WHEN e.high THEN interval '30 seconds' ELSE interval '60 seconds' END,
               cardinality(e.ids)
        FROM evidence e JOIN patients p ON p.id=e.patient_id RETURNING id,patient_id,original_assessment_id
    ) INSERT INTO alert_events (alert_id,event_type,assessment_id)
      SELECT a.id,CASE WHEN item.id=a.original_assessment_id THEN 'opened' ELSE 'updated' END,item.id
      FROM episodes a JOIN evidence e ON e.patient_id=a.patient_id
      CROSS JOIN LATERAL unnest(e.ids) WITH ORDINALITY item(id,position) ORDER BY a.id,item.position""")


def downgrade() -> None:
    # Existing M3 episodes intentionally prevent a lossy downgrade.
    op.execute("""ALTER TABLE alert_events DROP CONSTRAINT alert_events_event_type_check,
        ADD CHECK (event_type IN ('opened','updated','acknowledged','reopened','escalated'))""")
    op.execute("""ALTER TABLE alerts DROP CONSTRAINT alerts_kind_check, DROP CONSTRAINT alerts_status_check,
        DROP CONSTRAINT alerts_check, DROP CONSTRAINT alerts_check1, DROP CONSTRAINT alerts_check2,
        DROP CONSTRAINT alerts_check3, DROP COLUMN resolved_at,
        ALTER original_assessment_id SET NOT NULL, ALTER latest_assessment_id SET NOT NULL,
        ADD CHECK (kind='risk'), ADD CHECK (status IN ('open','acknowledged')),
        ADD CHECK ((status='acknowledged') = (acknowledged_at IS NOT NULL)),
        ADD CHECK ((status='acknowledged') = (acknowledged_by IS NOT NULL))""")
    op.execute("ALTER TABLE patients DROP gap_recovery_count, DROP last_complete_at, DROP last_known_assessment_id")
