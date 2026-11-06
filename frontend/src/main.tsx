import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import "./style.css";

async function checkReadiness({ signal }: { signal: AbortSignal }): Promise<string> {
  const response = await fetch("/health/ready", { signal, cache: "no-store" });
  if (response.status === 503) return "Service unready";
  if (!response.ok) throw new Error("Health check failed");
  return "Service ready";
}

function Shell() {
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

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");
createRoot(root).render(
  <QueryClientProvider client={new QueryClient()}><Shell /></QueryClientProvider>,
);
