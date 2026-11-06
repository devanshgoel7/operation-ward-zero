import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { acknowledgeAlert } from "../api/monitoring";
import type { components } from "../api/schema";

type Schemas = components["schemas"];
type Assessment = Schemas["Assessment"];

const metricNames: Record<string, string> = {
  heart_rate_bpm: "Heart rate", spo2_pct: "Oxygen saturation", systolic_mmhg: "Systolic pressure",
  diastolic_mmhg: "Diastolic pressure", temperature_c: "Temperature",
};

function Evidence({ assessment }: { assessment: Assessment }) {
  return <>
    <ul className="findings">{assessment.findings.map(f => <li key={f.rule_id}>
      <b>{metricNames[f.metric]}</b> {f.value} {f.unit} · {f.priority} when {f.condition} {f.unit}
      <br/><small>Observed {new Date(f.observed_at).toLocaleString()} · Rule {f.rule_id}</small>
    </li>)}</ul>
    <small className="source">{assessment.rule_version} · {assessment.data_quality === "incomplete"
      ? "Incomplete reading" : "Complete reading"} · Reading {assessment.reading_id}</small>
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
    <div className="episode-heading"><h3>{patient}</h3><span>{alert.peak_priority} peak concern</span></div>
    <p>{backup ? "Escalated to backup caregiver" : "Assigned to primary caregiver"} {assignee} · {alert.status === "open" ? "Awaiting acknowledgement" :
      `Acknowledged by ${assignee} at ${new Date(alert.acknowledged_at!).toLocaleString()}`}</p>
    <h4>Latest alert evidence <span className="severity" data-level={alert.latest_assessment.concern}>{alert.latest_assessment.concern}</span></h4>
    <Evidence assessment={alert.latest_assessment}/>
    {alert.original_assessment.id !== alert.latest_assessment.id && <details>
      <summary>Opening evidence <span className="severity" data-level={alert.original_assessment.concern}>{alert.original_assessment.concern}</span></summary><Evidence assessment={alert.original_assessment}/>
    </details>}
    {alert.status === "open" && <button type="button" disabled={actor !== alert.assignee_id || action.isPending}
      onClick={() => action.mutate()}>{action.isPending ? "Saving acknowledgement…" : "Acknowledge"}</button>}
    {action.isError && <p role="alert">{action.error.message}</p>}
  </article>;
}

export function RiskAlerts({ dashboard }: { dashboard: Schemas["Dashboard"] }) {
  const [selection, setSelection] = useState("");
  const actor = selection || dashboard.caregivers[0]?.id || "";
  const assignedAlerts = dashboard.active_alerts.filter(alert => alert.assignee_id === actor);
  return <section className="risk-panel" aria-labelledby="risk-heading">
    <div className="episode-heading"><div><h2 id="risk-heading">Caregiver inbox</h2>
      <p>Thresholds use fictional demonstration settings.</p></div>
      <label>Demo caregiver <select value={actor} onChange={e => setSelection(e.target.value)}>
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
