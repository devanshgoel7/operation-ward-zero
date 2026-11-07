import { useMutation, useQueryClient } from "@tanstack/react-query";
import { acknowledgeAlert } from "../api/monitoring";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
type Assessment = Schemas["Assessment"];

const metricNames: Record<string, string> = {
  heart_rate_bpm: "Heart rate", spo2_pct: "Oxygen saturation", systolic_mmhg: "Systolic pressure",
  diastolic_mmhg: "Diastolic pressure", temperature_c: "Temperature",
};

export function Evidence({ assessment }: { assessment: Assessment }) {
  return <>
    <ul className="findings">{assessment.findings.map(f => <li key={f.rule_id}>
      <b>{metricNames[f.metric] ?? f.metric.replaceAll("_", " ")}</b> {f.value} {f.unit} · {f.priority} when {f.condition}
      <br/><small>Observed {new Date(f.observed_at).toLocaleString()} · Rule {f.rule_id}</small>
      {(f.observations ?? []).map(o => <p key={o.observation_id} className="source">
        Observation {o.observation_id} · {o.tag.replaceAll("_", " ")} · actor {o.caregiver_id}
        {o.note && <> · Note: {o.note}</>}
      </p>)}
      {(f.evidence ?? []).length > 0 && <details><summary>Stored reading evidence ({f.evidence!.length})</summary>
        <ul>{f.evidence!.map(e => <li className="source" key={e.reading_id}>
          {e.value} · {new Date(e.observed_at).toLocaleString()} · {e.reading_id}
        </li>)}</ul>
      </details>}
    </li>)}</ul>
    <small className="source">{assessment.rule_version} · {assessment.data_quality} data ·
      {assessment.scope === "historical" ? " Historical reading" : " Reading"} {assessment.reading_id ?? "unavailable"}
      {assessment.observation_id && <> · Trigger observation {assessment.observation_id}</>}</small>
  </>;
}

function Episode({ alert, actor, patient, assignee, backup }: {
  alert: Schemas["Alert"]; actor: string; patient: string; assignee: string; backup: boolean;
}) {
  const cache = useQueryClient();
  const action = useMutation({
    mutationFn: () => acknowledgeAlert(alert.id, actor),
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ["dashboard"] }); },
  });
  return <article className="episode" data-priority={alert.peak_priority}>
    <div className="episode-heading"><h3>{patient}</h3><span>{alert.peak_priority} priority</span></div>
    <strong>{{ risk: "Risk concern", monitoring_gap: "Monitoring gap", delayed_review: "Delayed review" }[alert.kind]}</strong>
    {alert.kind === "monitoring_gap" && <p>Opened after 30 seconds without a complete reading. Three consecutive fresh complete readings close this gap.</p>}
    <p>{backup ? "Escalated to backup caregiver" : "Assigned to primary caregiver"} {assignee} · {alert.status === "open" ? "Awaiting acknowledgement" :
      `Acknowledged by ${assignee} at ${new Date(alert.acknowledged_at!).toLocaleString()}`}</p>
    {alert.latest_assessment && <><h4>Latest alert evidence <span className="severity" data-level={alert.latest_assessment.concern}>{alert.latest_assessment.concern}</span></h4>
    <Evidence assessment={alert.latest_assessment}/></>}
    {alert.original_assessment && alert.original_assessment.id !== alert.latest_assessment?.id && <details>
      <summary>Opening evidence <span className="severity" data-level={alert.original_assessment.concern}>{alert.original_assessment.concern}</span></summary><Evidence assessment={alert.original_assessment}/>
    </details>}
    {alert.status === "open" && <button type="button" disabled={actor !== alert.assignee_id || action.isPending}
      onClick={() => action.mutate()}>{action.isPending ? "Saving acknowledgement…" : "Acknowledge"}</button>}
    {action.isError && <p role="alert">{action.error.message}</p>}
  </article>;
}

export function RiskAlerts({ dashboard, actor, onActorChange }: {
  dashboard: Schemas["Dashboard"]; actor: string; onActorChange: (actor: string) => void;
}) {
  const assignedAlerts = dashboard.active_alerts.filter(alert => alert.assignee_id === actor);
  return <section className="risk-panel" aria-labelledby="risk-heading">
    <div className="episode-heading"><div><h2 id="risk-heading">Caregiver inbox</h2>
      <p>Rules use fictional demonstration settings. The selector provides attribution, not authentication.</p></div>
      <label>Demo caregiver <select value={actor} onChange={e => onActorChange(e.target.value)}>
        {dashboard.caregivers.map(c => <option key={c.id} value={c.id}>{c.display_name}</option>)}
      </select></label>
    </div>
    {assignedAlerts.length === 0 && <p>No alerts assigned to this caregiver.</p>}
    {assignedAlerts.map(alert => <Episode key={alert.id} alert={alert} actor={actor}
      backup={dashboard.patients.some(p => p.patient.id === alert.patient_id && p.patient.backup_caregiver_id === alert.assignee_id)}
      patient={dashboard.patients.find(p => p.patient.id === alert.patient_id)!.patient.display_name}
      assignee={dashboard.caregivers.find(c => c.id === alert.assignee_id)!.display_name}/>)}
  </section>;
}
