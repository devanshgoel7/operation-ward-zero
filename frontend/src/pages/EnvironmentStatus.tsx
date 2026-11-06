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
    <>
      <header><span className="mark" aria-hidden="true">+</span>Operation Ward Zero</header>
      <main>
        <p className="context">Local development</p>
        <h1>Environment status</h1>
        <section aria-label="Application health">
          <div>
            <h2>Application readiness</h2>
            <p>Checks the PostgreSQL connection and migration version.</p>
          </div>
          <strong role="status" data-ready={status === "Service ready"}>{status}</strong>
        </section>
        <nav aria-label="Developer tools">
          <a href="/openapi.json">OpenAPI contract</a>
          <a href="/health/ready">Readiness response</a>
        </nav>
      </main>
    </>
  );
}
