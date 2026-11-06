export async function checkReadiness({ signal }: { signal: AbortSignal }): Promise<string> {
  const response = await fetch("/health/ready", { signal, cache: "no-store" });
  if (response.status === 503) return "Service unready";
  if (!response.ok) throw new Error("Health check failed");
  return "Service ready";
}
