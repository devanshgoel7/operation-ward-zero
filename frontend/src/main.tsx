import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EnvironmentStatus } from "./pages/EnvironmentStatus";
import "./styles/global.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing application root");
createRoot(root).render(
  <QueryClientProvider client={new QueryClient()}><EnvironmentStatus /></QueryClientProvider>,
);
