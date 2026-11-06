import { useQuery } from "@tanstack/react-query";
import { checkReadiness } from "../api/health";

export function EnvironmentStatus() {
  const query = useQuery({
    queryKey: ["readiness"],
    queryFn: checkReadiness,
    retry: false,
    refetchInterval: 15000,
  });
  const status = query.isError ? "Service unreachable" : query.data ?? "Checking service…";
  return (
    <footer>
        <h2>Environment status</h2>
        <section aria-label="Application health">
          <div>
            <h3>Application readiness</h3>
            <p>Checks the PostgreSQL connection and migration version.</p>
          </div>
          <strong role="status" data-ready={status === "Service ready"}>{status}</strong>
        </section>
        <nav aria-label="Developer tools">
          <a href="/openapi.json">OpenAPI contract</a>
          <a href="/health/ready">Readiness response</a>
        </nav>
    </footer>
  );
}
