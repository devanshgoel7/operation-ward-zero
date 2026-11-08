import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSync } from "../api/Realtime";
import { fetchDashboard, type PatientSnapshot } from "../api/monitoring";
import type { components } from "../api/schema";
import { DashboardHeader, DashboardShell, Icon, Panel, StatusBadge } from "../components/DashboardShell";
import { AssessmentRisk, lastKnownRiskLabels } from "../components/AssessmentRisk";
import { OverviewMetrics, ReadingQuality } from "../components/MonitoringOverview";
import { VitalHistory } from "../components/VitalHistory";
import { EnvironmentStatus } from "./EnvironmentStatus";
import { RiskAlerts } from "./RiskAlerts";
import { PatientContext } from "./PatientContext";

function timestamp(value: string) {
  return <time dateTime={value}>{new Date(value).toLocaleString()}</time>;
}

const patientSelectionKey = "wardzero.selected-patient";

function PatientPicker({ patients, patientId, onSelect }: {
  patients: PatientSnapshot[]; patientId: string; onSelect: (id: string) => void;
}) {
  return <label className="patient-picker">
    <span>Selected patient</span>
    <select value={patientId} onChange={event => onSelect(event.target.value)}>
      {patients.map(({ patient }) => <option key={patient.id} value={patient.id}>{patient.display_name}</option>)}
    </select>
  </label>;
}

function PatientRow({ snapshot, selected, outdated, pendingRisk, onReview }: {
  snapshot: PatientSnapshot; selected: boolean; outdated: boolean; pendingRisk?: components["schemas"]["Alert"];
  onReview: (id: string) => void;
}) {
  const { patient, latest_reading: reading, data_quality: quality } = snapshot;
  const assessment = outdated ? null : snapshot.current_assessment;
  const retainedRisk = pendingRisk?.pending_risk_assessment;
  const showLastKnown = !retainedRisk && (!assessment || assessment.concern === null);
  const initials = patient.display_name.split(/\s+/).slice(0, 2).map(name => name[0]).join("");
  return <article data-reading-id={reading?.reading_id}>
    <div className="patient-identity">
      <span className="patient-initials" aria-hidden="true">{initials}</span>
      <div className="patient-name">
        <h3>{patient.display_name}</h3>
        {selected && <span className="patient-selected"><Icon name="check"/> Selected patient</span>}
        <button className="patient-review" type="button" aria-label={`Review patient ${patient.display_name}`}
          aria-current={selected || undefined} onClick={() => onReview(patient.id)}>Review patient <Icon name="arrow"/></button>
      </div>
    </div>
    <dl className="patient-vitals">
      <div><dt>Heart rate</dt><dd>{reading?.heart_rate_bpm ?? "—"} <small>bpm</small></dd></div>
      <div><dt>Oxygen saturation</dt><dd>{reading?.spo2_pct ?? "—"} <small>%</small></dd></div>
      <div><dt>Blood pressure</dt><dd>{reading?.systolic_mmhg ?? "—"} / {reading?.diastolic_mmhg ?? "—"} <small>mmHg</small></dd></div>
      <div><dt>Temperature</dt><dd>{reading?.temperature_c ?? "—"} <small>°C</small></dd></div>
    </dl>
    <div className="patient-status">
      <div><span className="visually-hidden">Data quality </span><StatusBadge tone={outdated ? "unknown" : quality}>
        {outdated ? "Unknown — showing cached data" : quality}</StatusBadge></div>
    </div>
    <div className="patient-reading-detail">
      <p className="patient-risk">
        <AssessmentRisk assessment={retainedRisk ?? assessment} quality={quality} unverified={outdated && !retainedRisk}/>
        {pendingRisk && <span className="pending-risk">{" · "}{outdated ? "Last received status · " : ""}Awaiting acknowledgement by{" "}
          {pendingRisk.assignee_id === patient.backup_caregiver_id ? "Backup caregiver" : "Primary caregiver"}.</span>}
      </p>
      {snapshot.delivery_delayed && <p>Delayed delivery · over 10 seconds</p>}
      {showLastKnown && snapshot.last_known_concern && snapshot.last_known_observed_at &&
        <p>Last known concern · {lastKnownRiskLabels[snapshot.last_known_concern]} at {timestamp(snapshot.last_known_observed_at)}</p>}
      {reading && assessment?.reading_id === reading.reading_id && assessment.data_quality === "incomplete" &&
        <p>Incomplete reading</p>}
      {reading && <p className="times"><span>Observed {timestamp(reading.observed_at)}</span><span>Received {timestamp(reading.received_at)}</span></p>}
    </div>
  </article>;
}

const connectionLabels = {
  connected: "Live updates connected",
  reconciling: "Reconnected — refreshing saved state…",
  connecting: "Connecting live updates — polling every five seconds",
  disconnected: "Live updates disconnected — polling every five seconds",
};

export function Monitoring() {
  const { connection, interval } = useSync();
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const [selectedActor, setSelectedActor] = useState("");
  const [selectedPatient, setSelectedPatient] = useState(() => sessionStorage.getItem(patientSelectionKey) ?? "");
  const [search, setSearch] = useState("");
  const query = useQuery({
    queryKey: ["dashboard"], queryFn: fetchDashboard, refetchInterval: interval, retry: false, networkMode: "always",
  });
  const dashboard = query.data;
  const outdated = query.isError || (!!dashboard && now - query.dataUpdatedAt > 20000);
  const caregivers = dashboard?.caregivers ?? [];
  const actor = caregivers.find(caregiver => caregiver.id === selectedActor)?.id ?? caregivers[0]?.id ?? "";
  const patients = dashboard?.patients ?? [];
  const pendingRisks = new Map(dashboard?.active_alerts.filter(alert => alert.kind === "risk" && alert.status === "open")
    .map(alert => [alert.patient_id, alert]));
  const selected = patients.find(snapshot => snapshot.patient.id === selectedPatient) ?? patients[0];
  const filter = search.trim().toLocaleLowerCase();
  const visiblePatients = patients.filter(snapshot => snapshot.patient.display_name.toLocaleLowerCase().includes(filter));
  const picker = selected && <PatientPicker patients={patients} patientId={selected.patient.id} onSelect={selectPatient}/>;

  function selectPatient(id: string) {
    setSelectedPatient(id);
    sessionStorage.setItem(patientSelectionKey, id);
  }

  function reviewPatient(id: string) {
    selectPatient(id);
    location.hash = "vital-signs";
    document.getElementById("vital-signs")?.focus();
  }

  return <DashboardShell header={<DashboardHeader search={search} onSearch={setSearch} caregivers={caregivers}
    actor={actor} onActorChange={setSelectedActor}/>}>
    <div className="page-heading">
      <div><h1>Patient monitoring</h1><p>Vital signs and caregiver response for synthetic adult patients.</p></div>
      <div className="sync-banner" data-connection={connection}>
        <div>
          <p role="status"><StatusBadge tone={connection === "connected" ? "fresh" : "incomplete"}>{connectionLabels[connection]}</StatusBadge></p>
          <p className="refresh-time"><Icon name="clock"/>{query.dataUpdatedAt ?
            <span>Last successful refresh {timestamp(new Date(query.dataUpdatedAt).toISOString())}</span> : "No patient snapshot received yet"}</p>
        </div>
        <button className="icon-button refresh-button" aria-label="Refresh now" type="button"
          onClick={() => void query.refetch()} disabled={query.isFetching}><Icon name="refresh"/></button>
      </div>
    </div>
    {query.isPending && <p className="notice" role="status">Loading patients…</p>}
    {query.isError && <p className="notice error-notice" role="alert">Refresh failed. Last received readings are shown when available.</p>}
    {outdated && <p className="cached-warning" role="status">Current state is unverified. Overview counts, reading quality, concern, observations and alerts reflect the last received snapshot when available.</p>}
    <p role="status" className="visually-hidden">{selected && `Selected patient: ${selected.patient.display_name}`}</p>
    <OverviewMetrics dashboard={dashboard} actor={actor} outdated={outdated}/>
    <Panel id="patients" title="Patient roster" className="roster-panel" description="Choose a patient to review vital signs and record observations."
      action={dashboard && <p className="roster-count" aria-live="polite">{filter ? `${visiblePatients.length} of ${patients.length} patients` : `${patients.length} patients`}</p>}>
      {visiblePatients.length > 0 ? <>
        <div className="roster-labels" aria-hidden="true">
          <span>Patient</span><span>Heart rate</span><span>Oxygen saturation</span><span>Blood pressure</span><span>Temperature</span><span>Monitoring status</span>
        </div>
        <div className="patients">{visiblePatients.map(snapshot => <PatientRow key={snapshot.patient.id}
          snapshot={snapshot} selected={snapshot.patient.id === selected?.patient.id}
          outdated={outdated} pendingRisk={pendingRisks.get(snapshot.patient.id)} onReview={reviewPatient}/>)}</div>
      </> : <p className="empty-state">{filter && dashboard ? "No patients match your search." : dashboard ? "No patients available." : "Waiting for the first patient snapshot."}</p>}
    </Panel>
    <div className="overview-charts">
      <Panel id="vital-signs" title="Vital signs overview" description="Review stored readings over time." className="vital-panel" action={picker}>
        {selected ? <>
          <div className="patient-actions">
            <a href="#patients">Back to patient roster</a>
            <a className="patient-action-primary" href="#record-observation"><Icon name="history"/> Record observation</a>
          </div>
          <VitalHistory key={selected.patient.id} patientId={selected.patient.id}/>
        </> : <p className="empty-state">{dashboard ? "No patients available." : "Waiting for the first patient snapshot."}</p>}
      </Panel>
      <ReadingQuality dashboard={dashboard} outdated={outdated}/>
    </div>
    <Panel id="patient-context" title="History and observations" description="Review trends and record observations for the selected patient."
      className="context-panel" action={picker}>
      {selected ? <PatientContext snapshot={selected} caregivers={caregivers} actor={actor} outdated={outdated}/> :
        <p className="empty-state">Select a patient when a snapshot is available.</p>}
    </Panel>
    <Panel id="caregiver-inbox" title="Caregiver inbox" className="risk-panel"
      description="Review assigned alerts and alerts for your primary patients, including backup escalations. The demo caregiver selector supplies attribution only.">
      {dashboard ? <RiskAlerts dashboard={dashboard} actor={actor} outdated={outdated}/> :
        <p className="empty-state">Waiting for the first alert snapshot.</p>}
    </Panel>
    <EnvironmentStatus/>
  </DashboardShell>;
}
