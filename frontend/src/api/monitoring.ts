import type { components } from "./schema";

export type PatientSnapshot = components["schemas"]["PatientSnapshot"];
export type ObservationInput = components["schemas"]["ObservationInput"];

export async function fetchHistory(patientId: string, signal: AbortSignal): Promise<components["schemas"]["ReadingPage"]> {
  const response = await fetch(`/api/v1/patients/${patientId}/readings?limit=2000`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Could not load patient history.");
  return response.json();
}

export async function saveObservation(patientId: string, actor: string, body: ObservationInput): Promise<void> {
  const response = await fetch(`/api/v1/patients/${patientId}/observations`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Caregiver-Id": actor },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.error?.message ?? "Could not confirm observation. Retry the saved draft.");
  }
}

export async function fetchDashboard({ signal }: { signal: AbortSignal }): Promise<components["schemas"]["Dashboard"]> {
  const response = await fetch("/api/v1/dashboard", { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Could not load patient readings.");
  return response.json();
}

export async function acknowledgeAlert(alertId: string, actor: string): Promise<void> {
  const key = `wardzero.ack.${alertId}.${actor}`;
  const command = sessionStorage.getItem(key) ?? crypto.randomUUID();
  sessionStorage.setItem(key, command);
  const response = await fetch(`/api/v1/alerts/${alertId}/acknowledge`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Caregiver-Id": actor },
    body: JSON.stringify({ command_id: command }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.error?.message ?? "Could not save acknowledgement. Retry to confirm.");
  }
  sessionStorage.removeItem(key);
}

export async function fetchAlert(alertId: string, signal: AbortSignal): Promise<components["schemas"]["AlertDetail"]> {
  const response = await fetch(`/api/v1/alerts/${alertId}`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Could not load lifecycle history.");
  return response.json();
}

export async function fetchResolvedAlerts(actor: string, signal: AbortSignal): Promise<components["schemas"]["AlertPage"]> {
  const response = await fetch(`/api/v1/alerts?status=resolved&assignee_id=${actor}&limit=50`, { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Could not load resolved alerts.");
  return response.json();
}

export async function resolveAlert(alertId: string, actor: string, body: components["schemas"]["Resolve"]): Promise<void> {
  const response = await fetch(`/api/v1/alerts/${alertId}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Demo-Caregiver-Id": actor },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null);
    throw new Error(result?.error?.message ?? "Could not confirm resolution. Retry the saved note.");
  }
}
