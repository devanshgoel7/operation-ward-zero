import type { components } from "./schema";

export type PatientSnapshot = components["schemas"]["PatientSnapshot"];

export async function fetchDashboard({ signal }: { signal: AbortSignal }): Promise<components["schemas"]["Dashboard"]> {
  const response = await fetch("/api/v1/dashboard", { signal, cache: "no-store" });
  if (!response.ok) throw new Error("Could not load patient readings.");
  return response.json();
}
