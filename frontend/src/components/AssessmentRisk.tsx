import type { components } from "../api/schema";
import { StatusBadge } from "./DashboardShell";

type Assessment = components["schemas"]["Assessment"];
type Finding = components["schemas"]["Finding"];

export const lastKnownRiskLabels = { none: "No risk", watch: "Watch", high: "High risk" } as const;

const metricNames: Partial<Record<string, string>> = {
  heart_rate_bpm: "Heart rate", spo2_pct: "Oxygen saturation", systolic_mmhg: "Systolic pressure",
  diastolic_mmhg: "Diastolic pressure", temperature_c: "Temperature",
};

export function assessmentMetricName(metric: string) {
  return metricNames[metric] ?? metric.replaceAll("_", " ");
}

function findingReason(finding: Finding) {
  const metric = assessmentMetricName(finding.metric);
  if (finding.rule_id === "breathlessness.spo2.high") {
    return "Caregiver recorded breathlessness alongside low or falling oxygen saturation.";
  }
  if (finding.rule_id.startsWith("observation.")) return `Caregiver recorded ${metric}.`;
  if (finding.rule_id.endsWith(".trend.watch")) {
    return `${metric} ${finding.value < 0 ? "fell" : "rose"} ${Math.abs(finding.value)} ${finding.unit}.`;
  }
  const comparison = finding.condition[0];
  if (comparison === "<" || comparison === ">") {
    const measurement = `${finding.value}${finding.unit === "%" ? "" : " "}${finding.unit}`;
    return `${metric} was ${comparison === "<" ? "below" : "above"} the demo limit (${measurement}).`;
  }
  return "A configured demo rule raised concern.";
}

const unknownReasons = {
  fresh: "Current assessment unavailable.",
  incomplete: "Insufficient measurements.",
  stale: "Vital readings are stale.",
  unavailable: "No vital readings available.",
};

export function AssessmentRisk({ assessment, quality = assessment?.data_quality ?? "fresh", unverified = false }: {
  assessment: Assessment | null; quality?: Assessment["data_quality"]; unverified?: boolean;
}) {
  const concern = unverified ? null : assessment?.concern ?? null;
  let label = "Unknown risk";
  let reason: string;
  if (concern === null) {
    reason = unverified ? "Current risk is unverified while showing cached data." : unknownReasons[quality];
  } else if (concern === "none") {
    label = "No risk";
    reason = "No configured concern detected";
  } else {
    const findings = assessment?.findings.filter(item => item.priority === concern) ?? [];
    const first = findings[0];
    reason = first ? findingReason(first) : "A configured demo rule raised concern.";
    if (concern === "high") {
      label = "High risk";
    } else {
      const signalCount = new Set(findings.map(item => item.metric)).size;
      label = signalCount >= 2 ? "Medium risk" : "Low risk";
      if (signalCount >= 2) reason = `${signalCount} distinct Watch signals. ${reason}`;
    }
  }

  return <span className="assessment-risk">
    <StatusBadge tone={concern ?? "unknown"}>{label}</StatusBadge>{" "}
    <span className="assessment-risk-reason">{reason}</span>
  </span>;
}
