import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { saveObservation, type ObservationInput, type PatientSnapshot } from "../api/monitoring";
import type { components } from "../api/schema";
import { Evidence } from "./RiskAlerts";
import { vitalMetrics, type VitalMetric } from "../components/VitalHistory";

const tags = { breathlessness: "Breathlessness", dizziness: "Dizziness", reduced_intake: "Reduced intake" } as const;

function ObservationForm({ snapshot, actor, caregiverName }: { snapshot: PatientSnapshot; actor: string; caregiverName?: string }) {
  const key = `wardzero.observation.${snapshot.patient.id}.${actor}`;
  const [saved, setSaved] = useState<ObservationInput | null>(() => {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) as ObservationInput : null;
  });
  const [tag, setTag] = useState<ObservationInput["tag"]>(saved?.tag ?? "breathlessness");
  const [present, setPresent] = useState(saved?.present ?? true);
  const [note, setNote] = useState(saved?.note ?? "");
  const cache = useQueryClient();
  const action = useMutation({
    networkMode: "always",
    mutationFn: (body: ObservationInput) => saveObservation(snapshot.patient.id, actor, body),
    onSuccess: async () => {
      sessionStorage.removeItem(key); setSaved(null); setNote("");
      await cache.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const allowed = [snapshot.patient.primary_caregiver_id, snapshot.patient.backup_caregiver_id].includes(actor);
  return <form id="record-observation" className="observation-form" aria-labelledby="record-observation-heading" tabIndex={-1} onSubmit={e => {
    e.preventDefault();
    const body = saved ?? { observation_id: crypto.randomUUID(), tag, present, note: note || null };
    sessionStorage.setItem(key, JSON.stringify(body)); setSaved(body); action.mutate(body);
  }}>
    <h3 id="record-observation-heading">Record observation</h3>
    <p className="observation-target">Patient <strong>{snapshot.patient.display_name}</strong><br/>
      Demo caregiver <strong>{caregiverName ?? "Unavailable"}</strong></p>
    {allowed ? <p>Present tags apply for ten minutes. Notes are displayed as written.</p> :
      <p>Select this patient's primary or backup demo caregiver to record an observation.</p>}
    <fieldset disabled={!!saved || action.isPending || !allowed}>
      <label>Observation tag <select value={tag} onChange={e => setTag(e.target.value as ObservationInput["tag"])}>
        {Object.entries(tags).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Observation state <select value={String(present)} onChange={e => setPresent(e.target.value === "true")}>
        <option value="true">Present</option><option value="false">Absent / clear this tag</option>
      </select></label>
      <label>Optional note (maximum 500 characters)
        <textarea maxLength={500} value={note} onChange={e => setNote(e.target.value)} />
      </label>
    </fieldset>
    <button type="submit" disabled={action.isPending || !allowed}>
      {action.isPending ? "Saving observation…" : saved ? "Retry saved observation" : "Save observation"}
    </button>
    {saved && !action.isPending && <button className="secondary-button" type="button" onClick={() => {
      sessionStorage.removeItem(key); setSaved(null); action.reset();
    }}>Discard draft</button>}
    {saved && !action.isPending && <p>The result is unconfirmed. Retry uses the same ID; discarding cannot undo a server save.</p>}
    {action.isError && <p role="alert">{action.error.message} Draft retained.</p>}
    {action.isSuccess && <p role="status">Observation saved.</p>}
  </form>;
}

export function PatientContext({ snapshot, caregivers, actor, outdated }: {
  snapshot: PatientSnapshot; caregivers: components["schemas"]["Caregiver"][]; actor: string; outdated: boolean;
}) {
  return <>
    {outdated && <p className="cached-warning">Cached context — trend findings and observation activity are unverified until refresh succeeds.</p>}
    <div className="context-columns">
      <div>
        <h3>{outdated ? "Last received trend context" : "Current trend context"}</h3>
        <p>Demonstration settings: adjacent one-minute medians, at least eight valid samples per window, no gap over ten seconds.</p>
        {(snapshot.current_assessment?.trend_summary ?? []).map(t => <div key={t.metric} className="trend-summary">
          <b>{vitalMetrics[t.metric as VitalMetric]?.[0] ?? t.metric}</b>: {t.status === "calculated"
            ? `${t.earlier_median} → ${t.recent_median}; change ${t.change! > 0 ? "+" : ""}${t.change} ${t.unit}`
            : `Insufficient continuous history (${t.status.replaceAll("_", " ")})`}
          <small> · Samples {t.earlier_count} / {t.recent_count} · Maximum gap {t.max_gap_seconds}s</small>
          <p className="times">{new Date(t.start).toLocaleTimeString()} → {new Date(t.midpoint).toLocaleTimeString()} → {new Date(t.end).toLocaleTimeString()}</p>
        </div>)}
        {!snapshot.current_assessment && <p>Current assessment unavailable. History and active observations remain visible.</p>}
        {snapshot.current_assessment && <Evidence assessment={snapshot.current_assessment}/>}
        <h3 className="observation-heading">{outdated ? "Last received observations" : "Active observations"}</h3>
        {snapshot.active_observations.length === 0 ? <p>No active structured observations.</p> :
          <ul className="findings">{snapshot.active_observations.map(o => <li className="source" key={o.observation_id}>
            <b>{tags[o.tag]}</b> · {caregivers.find(c => c.id === o.caregiver_id)?.display_name}
            <br/>Recorded {new Date(o.created_at).toLocaleString()} · Expires {new Date(o.expires_at).toLocaleString()}
            {o.note && <p>Note: {o.note}</p>}<small>Observation {o.observation_id}</small>
          </li>)}</ul>}
      </div>
      <ObservationForm key={`${snapshot.patient.id}.${actor}`} snapshot={snapshot} actor={actor}
        caregiverName={caregivers.find(caregiver => caregiver.id === actor)?.display_name}/>
    </div>
  </>;
}
