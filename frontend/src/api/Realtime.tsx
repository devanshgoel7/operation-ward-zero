import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

type Connection = "connecting" | "reconciling" | "connected" | "disconnected";
const SyncContext = createContext<{ connection: Connection; interval: number }>({ connection: "connecting", interval: 5000 });
export const useSync = () => useContext(SyncContext);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const [connection, setConnection] = useState<Connection>("connecting");
  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let flushTimer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    let lastMessage = Date.now();
    let openedAt = Date.now();
    let flushing = false;
    let reconcileSocket: WebSocket | undefined;
    const pending = new Set<string>();
    const keys = ["dashboard", "history", "alert", "resolved-alerts", "readiness"];

    async function flush() {
      if (disposed || flushing) return;
      flushing = true;
      try {
        while (pending.size && !disposed) {
          const batch = [...pending]; pending.clear();
          // Serialize batches: a hint arriving during a fetch must cause a later fetch.
          await Promise.all(batch.map(key => cache.invalidateQueries({ queryKey: [key] }, { cancelRefetch: false })));
        }
        if (!disposed && reconcileSocket === socket && socket?.readyState === WebSocket.OPEN) {
          setConnection("connected"); reconcileSocket = undefined;
        }
      } finally { flushing = false; }
    }
    function queue(names: string[]) {
      names.forEach(name => pending.add(name));
      if (!flushTimer) flushTimer = setTimeout(() => { flushTimer = undefined; void flush(); }, 80);
    }
    function disconnect(current: WebSocket) {
      if (disposed || socket !== current) return;
      // A silent peer may never finish the close handshake. Switch to fallback
      // immediately instead of waiting for the browser's native close timeout.
      socket = undefined;
      current.onopen = current.onmessage = current.onerror = current.onclose = null;
      current.close();
      setConnection("disconnected"); reconcileSocket = undefined;
      queue(keys);
      retryTimer = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 15000));
    }
    function connect() {
      if (disposed) return;
      setConnection(attempts ? "disconnected" : "connecting");
      openedAt = lastMessage = Date.now();
      const current = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/v1/ws`);
      socket = current;
      current.onopen = () => {
        if (disposed || socket !== current) return;
        lastMessage = Date.now();
        setConnection("reconciling"); reconcileSocket = current;
        queue(keys);
      };
      current.onmessage = event => {
        if (disposed || socket !== current) return;
        try {
          const hint: unknown = JSON.parse(event.data);
          if (!hint || typeof hint !== "object" || !("type" in hint) || !("server_time" in hint) ||
              typeof hint.server_time !== "string" || !Number.isFinite(Date.parse(hint.server_time))) return;
          if (!["patient.updated", "alert.updated", "system.status", "heartbeat"].includes(String(hint.type))) return;
          lastMessage = Date.now(); attempts = 0;
          if (hint.type === "patient.updated") queue(["dashboard", "history"]);
          if (hint.type === "alert.updated") queue(["dashboard", "alert", "resolved-alerts"]);
          if (hint.type === "system.status") queue(["readiness"]);
        } catch { /* Ignore malformed hints. Polling remains authoritative. */ }
      };
      current.onerror = () => disconnect(current);
      current.onclose = () => disconnect(current);
    }
    function resume() {
      if (document.visibilityState === "hidden") return;
      queue(keys);
      if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 25000) disconnect(socket);
      else if (!socket || socket.readyState === WebSocket.CLOSED) { clearTimeout(retryTimer); connect(); }
    }
    const watchdog = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 25000) disconnect(socket);
      else if (socket?.readyState === WebSocket.CONNECTING && Date.now() - openedAt > 10000) disconnect(socket);
    }, 1000);
    window.addEventListener("online", resume);
    document.addEventListener("visibilitychange", resume);
    connect();
    return () => {
      disposed = true; clearTimeout(retryTimer); clearTimeout(flushTimer); clearInterval(watchdog);
      window.removeEventListener("online", resume);
      document.removeEventListener("visibilitychange", resume);
      socket?.close();
    };
  }, [cache]);
  return <SyncContext.Provider value={{ connection, interval: connection === "connected" ? 15000 : 5000 }}>
    {children}
  </SyncContext.Provider>;
}
