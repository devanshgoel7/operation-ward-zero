import { useQuery } from "@tanstack/react-query";
import { checkReadiness } from "../api/health";
import { useSync } from "../api/Realtime";
import { Panel, StatusBadge } from "../components/DashboardShell";

export function EnvironmentStatus() {
  const { interval } = useSync();
  const query = useQuery({
    queryKey: ["readiness"],
    queryFn: checkReadiness,
    retry: false,
    refetchInterval: interval, networkMode: "always",
  });
  const status = query.isError ? "Service unreachable" : query.data ?? "Checking service…";
  return <Panel id="system-health" title="System health" description="Application readiness"
    action={<div role="status"><StatusBadge tone={status === "Service ready" ? "fresh" : status === "Checking service…" ? "unknown" : "high"}>
      {status}</StatusBadge></div>}>
    <p>Checks PostgreSQL, migrations, and the freshness and deadline worker.</p>
    <nav className="developer-links" aria-label="Developer tools">
      <a href="/openapi.json">OpenAPI contract</a>
      <a href="/health/ready">Readiness response</a>
    </nav>
  </Panel>;
}
