import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { acknowledgeAlert, fetchAlert, fetchResolvedAlerts, resolveAlert } from "../api/monitoring";
import type { components } from "../api/schema";
import { useSync } from "../api/Realtime";

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

function ResolutionForm({ alert, actor }: { alert: Schemas["Alert"]; actor: string }) {
  const key = `wardzero.resolve.${alert.id}.${actor}`;
  const [saved, setSaved] = useState<Schemas["Resolve"] | null>(() => {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) as Schemas["Resolve"] : null;
  });
  const [note, setNote] = useState(saved?.note ?? "");
  const cache = useQueryClient();
  const action = useMutation({
    networkMode: "always",
    mutationFn: (body: Schemas["Resolve"]) => resolveAlert(alert.id, actor, body),
    onSuccess: async () => {
      sessionStorage.removeItem(key); setSaved(null); setNote("");
      await Promise.all([cache.invalidateQueries({ queryKey: ["dashboard"] }),
        cache.invalidateQueries({ queryKey: ["resolved-alerts"] }),
        cache.invalidateQueries({ queryKey: ["alert", alert.id] })]);
    },
  });
  if (alert.status !== "acknowledged" && !saved) return null;
  return <form onSubmit={e => {
    e.preventDefault();
    const body = saved ?? { command_id: crypto.randomUUID(), note };
    sessionStorage.setItem(key, JSON.stringify(body)); setSaved(body); action.mutate(body);
  }}>
    <label>Resolution note (required, maximum 500 characters)
      <textarea required maxLength={500} value={note} disabled={!!saved || action.isPending}
        onChange={e => setNote(e.target.value)}/>
    </label>
    <button type="submit" disabled={action.isPending || actor !== alert.assignee_id || !note.trim()}>
      {action.isPending ? "Saving resolution…" : saved ? "Retry saved resolution" : "Resolve alert"}
    </button>
    {saved && !action.isPending && <>
      <button type="button" onClick={() => {
        sessionStorage.removeItem(key); setSaved(null); action.reset();
      }}>Discard resolution draft</button>
      <p>The result is unconfirmed. Retry preserves the command and note; discarding cannot undo a server save.</p>
    </>}
    {action.isError && <p role="alert">{action.error.message} Note retained.</p>}
  </form>;
}

function LifecycleHistory({ alertId, caregivers }: { alertId: string; caregivers: Schemas["Caregiver"][] }) {
  const { interval } = useSync();
  const [expanded, setExpanded] = useState(false);
  const query = useQuery({ queryKey: ["alert", alertId],
    queryFn: ({ signal }) => fetchAlert(alertId, signal), enabled: expanded,
    refetchInterval: interval, retry: false, networkMode: "always" });
  return <details onToggle={e => setExpanded(e.currentTarget.open)}>
    <summary>Lifecycle history</summary>
    {query.isPending && <p role="status">Loading history…</p>}
    {query.isError && <p role="alert">{query.error.message}</p>}
    <ol>{query.data?.events.map(event => <li key={event.id}>
      <b>{event.event_type}</b> · {new Date(event.occurred_at).toLocaleString()}
      {event.caregiver_id && <> · {caregivers.find(c => c.id === event.caregiver_id)?.display_name ?? event.caregiver_id}</>}
      {typeof event.details.response_seconds === "number" && <p>
        Response: {event.details.response_seconds.toFixed(1)} seconds since opening/reopening;
        {" "}{Number(event.details.assignment_response_seconds).toFixed(1)} seconds since assignment.
      </p>}
      {event.details.note && <p>Resolution note: {event.details.note}</p>}
    </li>)}</ol>
  </details>;
}

function Episode({ alert, actor, patient, assignee, backup, caregivers }: {
  alert: Schemas["Alert"]; actor: string; patient: string; assignee: string; backup: boolean;
  caregivers: Schemas["Caregiver"][];
}) {
  const cache = useQueryClient();
  const [savedAck, setSavedAck] = useState(() => !!sessionStorage.getItem(`wardzero.ack.${alert.id}.${actor}`));
  const action = useMutation({
    networkMode: "always",
    mutationFn: () => acknowledgeAlert(alert.id, actor),
    onError: () => setSavedAck(true),
    onSuccess: async () => {
      setSavedAck(false);
      await cache.invalidateQueries({ queryKey: ["dashboard"] });
      await cache.invalidateQueries({ queryKey: ["alert", alert.id] });
    },
  });
  return <article className="episode" data-priority={alert.peak_priority} data-alert-id={alert.id}>
    <div className="episode-heading"><h3>{patient}</h3><span>{alert.peak_priority} priority</span></div>
    <strong>{{ risk: "Risk concern", monitoring_gap: "Monitoring gap", delayed_review: "Delayed review" }[alert.kind]}</strong>
    {alert.kind === "monitoring_gap" && <p>Opened after 30 seconds without a complete reading. Three consecutive fresh complete readings close this gap.</p>}
    <p>{backup ? "Escalated to backup caregiver" : "Assigned to primary caregiver"} {assignee} · {alert.status === "open" ? "Awaiting acknowledgement" :
      alert.status === "resolved" ? `Resolved at ${new Date(alert.resolved_at!).toLocaleString()}` :
      `Acknowledged by ${assignee} at ${new Date(alert.acknowledged_at!).toLocaleString()}`}</p>
    {alert.escalation_due_at && <p>Backup escalation due {new Date(alert.escalation_due_at).toLocaleTimeString()} · 30/60-second demonstration deadlines.</p>}
    {alert.status === "open" && backup && !alert.escalation_due_at && <p>Backup acknowledgement pending. No further escalation tier.</p>}
    {alert.kind === "risk" && alert.status !== "resolved" && <p>
      Recovery: {alert.recovery_count}/3 consecutive fresh complete readings with no firing rules.
      Resolution requires acknowledgement and a note; stale recovery cannot resolve an alert.
    </p>}
    {alert.kind === "delayed_review" && alert.status !== "resolved" && <p>Resolve after acknowledgement and a review note.</p>}
    {alert.latest_assessment && <><h4>Latest alert evidence <span className="severity" data-level={alert.latest_assessment.concern}>{alert.latest_assessment.concern}</span></h4>
    <Evidence assessment={alert.latest_assessment}/></>}
    {alert.original_assessment && alert.original_assessment.id !== alert.latest_assessment?.id && <details>
      <summary>Opening evidence <span className="severity" data-level={alert.original_assessment.concern}>{alert.original_assessment.concern}</span></summary><Evidence assessment={alert.original_assessment}/>
    </details>}
    {(alert.status === "open" || savedAck) && <button type="button" disabled={actor !== alert.assignee_id || action.isPending}
      onClick={() => action.mutate()}>{action.isPending ? "Saving acknowledgement…" : savedAck ? "Retry saved acknowledgement" : "Acknowledge"}</button>}
    {savedAck && !action.isPending && <p>Acknowledgement result unconfirmed. Retry uses the saved command, including if the server already accepted it.</p>}
    {action.isError && <p role="alert">{action.error.message} Acknowledgement is unconfirmed; retry retains the saved command.</p>}
    {alert.kind !== "monitoring_gap" && <ResolutionForm key={`${alert.id}.${actor}`} alert={alert} actor={actor}/>}
    <LifecycleHistory alertId={alert.id} caregivers={caregivers}/>
  </article>;
}

export function RiskAlerts({ dashboard, actor, onActorChange, outdated }: {
  dashboard: Schemas["Dashboard"]; actor: string; onActorChange: (actor: string) => void; outdated: boolean;
}) {
  const { interval } = useSync();
  const assignedAlerts = dashboard.active_alerts.filter(alert => alert.assignee_id === actor);
  const [showResolved, setShowResolved] = useState(false);
  const resolved = useQuery({ queryKey: ["resolved-alerts", actor],
    queryFn: ({ signal }) => fetchResolvedAlerts(actor, signal), enabled: showResolved,
    refetchInterval: interval, retry: false, networkMode: "always" });
  function renderEpisode(alert: Schemas["Alert"]) {
    return <Episode key={`${alert.id}.${actor}`} alert={alert} actor={actor} caregivers={dashboard.caregivers}
      backup={dashboard.patients.some(p => p.patient.id === alert.patient_id && p.patient.backup_caregiver_id === alert.assignee_id)}
      patient={dashboard.patients.find(p => p.patient.id === alert.patient_id)!.patient.display_name}
      assignee={dashboard.caregivers.find(c => c.id === alert.assignee_id)!.display_name}/>;
  }
  return <section className="risk-panel" aria-labelledby="risk-heading">
    <div className="episode-heading"><div><h2 id="risk-heading">Caregiver inbox</h2>
      <p>Rules use fictional demonstration settings. The selector provides attribution, not authentication.</p></div>
      <label>Demo caregiver <select value={actor} onChange={e => onActorChange(e.target.value)}>
        {dashboard.caregivers.map(c => <option key={c.id} value={c.id}>{c.display_name}</option>)}
      </select></label>
    </div>
    {outdated && <p className="cached-warning">Cached inbox — assignments, deadlines and recovery progress may have changed. Actions are confirmed by the server.</p>}
    {assignedAlerts.length === 0 && <p>{outdated ? "No assigned alerts in the last received snapshot." : "No alerts assigned to this caregiver."}</p>}
    {assignedAlerts.map(renderEpisode)}
    <label><input type="checkbox" checked={showResolved} onChange={e => setShowResolved(e.target.checked)}/> Show recently resolved alerts</label>
    {showResolved && <div>
      <p>Newest 50 resolved episodes for this caregiver. Full saved history remains available through the alerts API.</p>
      {resolved.isPending && <p role="status">Loading resolved alerts…</p>}
      {resolved.isError && <p role="alert">{resolved.error.message}</p>}
      {resolved.data?.items.map(renderEpisode)}
    </div>}
  </section>;
}
