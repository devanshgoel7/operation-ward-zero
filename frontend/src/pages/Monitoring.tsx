import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchDashboard, type PatientSnapshot } from "../api/monitoring";
import { EnvironmentStatus } from "./EnvironmentStatus";
import { RiskAlerts } from "./RiskAlerts";
import { PatientContext } from "./PatientContext";

function timestamp(value: string) {
  return <time dateTime={value}>{new Date(value).toLocaleString()}</time>;
}

function PatientCard({ snapshot, offline }: { snapshot: PatientSnapshot; offline: boolean }) {
  const { patient, latest_reading: reading, data_quality: quality } = snapshot;
  const assessment = offline ? null : snapshot.current_assessment;
  const showLastKnown = offline || !assessment || assessment.concern === null;
  return (
    <article data-reading-id={reading?.reading_id}>
      <h2>{patient.display_name}</h2>
      <p>Data quality · <strong>{offline ? "Refresh unavailable" : quality}</strong></p>
      {snapshot.delivery_delayed && <p>Delayed delivery · over 10 seconds</p>}
      {showLastKnown && snapshot.last_known_concern && snapshot.last_known_observed_at &&
        <p>Last known concern · {snapshot.last_known_concern} at {timestamp(snapshot.last_known_observed_at)}</p>}
      {assessment &&
        (assessment.concern === "watch" || assessment.concern === "high") &&
        <span className="severity" data-level={assessment.concern}>{assessment.concern} concern</span>}
      {reading ? <>
        <dl>
          <div><dt>Heart rate</dt><dd>{reading.heart_rate_bpm ?? "—"} <small>bpm</small></dd></div>
          <div><dt>Oxygen saturation</dt><dd>{reading.spo2_pct ?? "—"} <small>%</small></dd></div>
          <div><dt>Blood pressure</dt><dd>{reading.systolic_mmhg ?? "—"} / {reading.diastolic_mmhg ?? "—"} <small>mmHg</small></dd></div>
          <div><dt>Temperature</dt><dd>{reading.temperature_c ?? "—"} <small>°C</small></dd></div>
        </dl>
        {assessment?.reading_id === reading.reading_id ? <p className="assessment">
          {assessment.concern === "none" ? "No configured concern detected" :
            assessment.concern === null ? "Insufficient measurements" : null}
          {assessment.data_quality === "incomplete" && (assessment.concern === null ? " · Incomplete reading" : "Incomplete reading")}
        </p> : <p>Assessment unavailable for this reading</p>}
        <p className="times">Observed {timestamp(reading.observed_at)}<br/>Received {timestamp(reading.received_at)}</p>
      </> : <p>Waiting for first reading</p>}
    </article>
  );
}

export function Monitoring() {
  const [selection, setSelection] = useState("");
  const query = useQuery({
    queryKey: ["dashboard"], queryFn: fetchDashboard, refetchInterval: 5000, retry: false, networkMode: "always",
  });
  const actor = selection || query.data?.caregivers[0]?.id || "";
  return <>
    <header>
      <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
        <path d="M9 16h14M16 9v14" stroke="currentColor" strokeWidth="3" />
      </svg>
      Operation Ward Zero
    </header>
    <main>
      <p className="context">Synthetic adult patients</p>
      <h1>Patient monitoring</h1>
      {query.isPending && <p role="status">Loading patients…</p>}
      {query.isError && <p role="alert">Refresh failed. Last received readings are shown when available.</p>}
      <div className="patients">{query.data?.patients.map(snapshot =>
        <PatientCard key={snapshot.patient.id} snapshot={snapshot} offline={query.isError} />)}</div>
      {query.data && <>
        <RiskAlerts dashboard={query.data} actor={actor} onActorChange={setSelection}/>
        <PatientContext dashboard={query.data} actor={actor}/>
      </>}
      <EnvironmentStatus />
    </main>
  </>;
}
