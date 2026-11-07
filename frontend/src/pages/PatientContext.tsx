import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchHistory, saveObservation, type ObservationInput, type PatientSnapshot } from "../api/monitoring";
import type { components } from "../api/schema";
import { Evidence } from "./RiskAlerts";

const metrics = {
  spo2_pct: ["Oxygen saturation", "%"], heart_rate_bpm: ["Heart rate", "bpm"],
  systolic_mmhg: ["Systolic pressure", "mmHg"], diastolic_mmhg: ["Diastolic pressure", "mmHg"],
  temperature_c: ["Temperature", "°C"],
} as const;
type Metric = keyof typeof metrics;
const tags = { breathlessness: "Breathlessness", dizziness: "Dizziness", reduced_intake: "Reduced intake" } as const;

function ObservationForm({ snapshot, actor }: { snapshot: PatientSnapshot; actor: string }) {
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
    mutationFn: (body: ObservationInput) => saveObservation(snapshot.patient.id, actor, body),
    onSuccess: async () => {
      sessionStorage.removeItem(key); setSaved(null); setNote("");
      await cache.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  const allowed = [snapshot.patient.primary_caregiver_id, snapshot.patient.backup_caregiver_id].includes(actor);
  return <form onSubmit={e => {
    e.preventDefault();
    const body = saved ?? { observation_id: crypto.randomUUID(), tag, present, note: note || null };
    sessionStorage.setItem(key, JSON.stringify(body)); setSaved(body); action.mutate(body);
  }}>
    <h3>Record observation</h3>
    <p>Uses the selected demo caregiver. Notes are displayed without interpretation. Present tags apply for ten minutes.</p>
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
    {saved && !action.isPending && <button type="button" onClick={() => {
      sessionStorage.removeItem(key); setSaved(null); action.reset();
    }}>Discard draft</button>}
    {saved && !action.isPending && <p>The result is unconfirmed. Retry uses the same ID; discarding cannot undo a server save.</p>}
    {action.isError && <p role="alert">{action.error.message} Draft retained.</p>}
    {action.isSuccess && <p role="status">Observation saved.</p>}
  </form>;
}

function History({ patientId }: { patientId: string }) {
  const [metric, setMetric] = useState<Metric>("spo2_pct");
  const query = useQuery({ queryKey: ["history", patientId],
    queryFn: ({ signal }) => fetchHistory(patientId, signal), refetchInterval: 5000, retry: false, networkMode: "always" });
  const rows = [...(query.data?.items ?? [])].reverse();
  const points: { time: number; value: number | null }[] = [];
  rows.forEach((reading, index) => {
    const time = Date.parse(reading.observed_at);
    if (index > 0 && time - Date.parse(rows[index - 1].observed_at) > 10000) {
      points.push({ time: time - 1, value: null });
    }
    points.push({ time, value: reading[metric] });
  });
  return <div className="history">
    <h3>Reading history</h3>
    <label>Chart metric <select value={metric} onChange={e => setMetric(e.target.value as Metric)}>
      {Object.entries(metrics).map(([value, [label, unit]]) => <option key={value} value={value}>{label} ({unit})</option>)}
    </select></label>
    <p>Last 30 minutes by observation time · {rows.length} stored readings. Missing measurements and gaps over ten seconds break the line.</p>
    {query.isPending && <p role="status">Loading history…</p>}
    {query.isError && <p role="alert">History refresh failed. Previously fetched history may be outdated.</p>}
    {query.data?.next_cursor && <p>Showing only the newest 2,000 readings in this interval.</p>}
    {!query.isPending && !query.isError && rows.length === 0 && <p>No readings in this interval.</p>}
    {rows.length > 0 && <div className="history-chart" role="img" aria-label={`${metrics[metric][0]} history from stored readings`}>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={points} margin={{ top: 15, right: 25, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} tickFormatter={v => new Date(v).toLocaleTimeString()} />
          <YAxis domain={["auto", "auto"]} width={60} unit={metrics[metric][1]} />
          <Tooltip labelFormatter={v => new Date(Number(v)).toLocaleString()} />
          <Line dataKey="value" name={metrics[metric][0]} unit={metrics[metric][1]} type="linear" stroke="#205e53"
            dot={false} connectNulls={false} isAnimationActive={false}/>
        </LineChart>
      </ResponsiveContainer>
    </div>}
  </div>;
}

export function PatientContext({ dashboard, actor }: { dashboard: components["schemas"]["Dashboard"]; actor: string }) {
  const [selected, setSelected] = useState("");
  const snapshot = dashboard.patients.find(p => p.patient.id === selected) ?? dashboard.patients[0];
  if (!snapshot) return null;
  return <section className="context-panel" aria-labelledby="context-heading">
    <h2 id="context-heading">History and observations</h2>
    <label>Selected patient <select value={snapshot.patient.id} onChange={e => setSelected(e.target.value)}>
      {dashboard.patients.map(p => <option key={p.patient.id} value={p.patient.id}>{p.patient.display_name}</option>)}
    </select></label>
    <History key={snapshot.patient.id} patientId={snapshot.patient.id}/>
    <h3>Current trend context</h3>
    <p>Demonstration settings: adjacent one-minute medians, at least eight valid samples per window, no gap over ten seconds.</p>
    {(snapshot.current_assessment?.trend_summary ?? []).map(t => <div key={t.metric} className="trend-summary">
      <b>{metrics[t.metric as Metric]?.[0] ?? t.metric}</b>: {t.status === "calculated"
        ? `${t.earlier_median} → ${t.recent_median}; change ${t.change! > 0 ? "+" : ""}${t.change} ${t.unit}`
        : `Insufficient continuous history (${t.status.replaceAll("_", " ")})`}
      <small> · Samples {t.earlier_count} / {t.recent_count} · Maximum gap {t.max_gap_seconds}s</small>
      <p className="times">{new Date(t.start).toLocaleTimeString()} → {new Date(t.midpoint).toLocaleTimeString()} → {new Date(t.end).toLocaleTimeString()}</p>
    </div>)}
    {!snapshot.current_assessment && <p>Current assessment unavailable. History and active observations remain visible.</p>}
    {snapshot.current_assessment && <Evidence assessment={snapshot.current_assessment}/>}
    <h3>Active observations</h3>
    {snapshot.active_observations.length === 0 && <p>No active structured observations.</p>}
    <ul>{snapshot.active_observations.map(o => <li className="source" key={o.observation_id}>
      <b>{tags[o.tag]}</b> · {dashboard.caregivers.find(c => c.id === o.caregiver_id)?.display_name}
      <br/>Recorded {new Date(o.created_at).toLocaleString()} · Expires {new Date(o.expires_at).toLocaleString()}
      {o.note && <p>Note: {o.note}</p>}<small>Observation {o.observation_id}</small>
    </li>)}</ul>
    <ObservationForm key={`${snapshot.patient.id}.${actor}`} snapshot={snapshot} actor={actor}/>
  </section>;
}
