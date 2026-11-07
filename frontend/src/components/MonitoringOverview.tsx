import { Pie, PieChart, ResponsiveContainer } from "recharts";
import type { components } from "../api/schema";
import { MetricCard, Panel } from "./DashboardShell";

type Dashboard = components["schemas"]["Dashboard"];

const qualityLegend = [
  { quality: "fresh", label: "Fresh", fill: "#b78bdd" },
  { quality: "incomplete", label: "Incomplete", fill: "#f2bd96" },
  { quality: "stale", label: "Stale", fill: "#a5bbeb" },
  { quality: "unavailable", label: "Unavailable", fill: "#e6d8ef" },
] as const;

export function OverviewMetrics({ dashboard, actor, outdated }: {
  dashboard: Dashboard | undefined; actor: string; outdated: boolean;
}) {
  const fresh = dashboard?.patients.filter(snapshot => snapshot.data_quality === "fresh").length;
  const assigned = dashboard?.active_alerts.filter(alert => alert.assignee_id === actor).length;
  const detail = (label: string) => !dashboard ? "Awaiting first snapshot" : outdated ? "Last received snapshot" : label;
  const caregiver = dashboard?.caregivers.find(candidate => candidate.id === actor);
  return <div className="overview-metrics">
    <MetricCard label="Monitored patients" value={dashboard?.patients.length} detail={detail("Synthetic patient roster")} icon="patients" accent="orange"/>
    <MetricCard label="Fresh readings" value={fresh} detail={detail("Patients with fresh data")} icon="pulse" accent="mint"/>
    <MetricCard label="Active alerts" value={dashboard?.active_alerts.length} detail={detail("Across all caregivers")} icon="alert" accent="lavender"/>
    <MetricCard label="Assigned alerts" value={assigned} detail={detail(caregiver?.display_name ?? "Selected demo caregiver")} icon="caregiver" accent="blue"/>
  </div>;
}

export function ReadingQuality({ dashboard, outdated }: { dashboard: Dashboard | undefined; outdated: boolean }) {
  const total = dashboard?.patients.length;
  const segments = qualityLegend.map(item => ({ ...item,
    value: dashboard?.patients.filter(snapshot => snapshot.data_quality === item.quality).length ?? 0,
  }));
  return <Panel id="reading-quality" title="Reading quality" className="quality-panel"
    description={outdated && dashboard ? "Last received quality by patient" : "Latest reading state by patient"}>
    {total ? <div className="quality-chart">
      <div className="quality-graphic" aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart accessibilityLayer={false}>
            <Pie data={segments.filter(segment => segment.value > 0)} dataKey="value" nameKey="label"
              innerRadius="69%" outerRadius="95%" startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}/>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="quality-total"><strong>{total}</strong><span>{total === 1 ? "patient" : "patients"}</span></div>
    </div> : <p className="empty-state">{dashboard ? "No patients in the snapshot." : "Waiting for the first snapshot."}</p>}
    <ul className="quality-legend" aria-label="Reading quality counts">
      {segments.map(item => <li key={item.quality}>
        <span aria-hidden="true" style={{ backgroundColor: item.fill }}/><span>{item.label}</span><strong>{dashboard ? item.value : "—"}</strong>
      </li>)}
    </ul>
  </Panel>;
}
