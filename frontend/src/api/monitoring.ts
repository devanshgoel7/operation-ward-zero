import type { components } from "./schema";

export type PatientSnapshot = components["schemas"]["PatientSnapshot"];

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
