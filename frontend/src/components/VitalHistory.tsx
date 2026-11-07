import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchHistory } from "../api/monitoring";
import { useSync } from "../api/Realtime";

export const vitalMetrics = {
  spo2_pct: ["Oxygen saturation", "%"], heart_rate_bpm: ["Heart rate", "bpm"],
  systolic_mmhg: ["Systolic pressure", "mmHg"], diastolic_mmhg: ["Diastolic pressure", "mmHg"],
  temperature_c: ["Temperature", "°C"],
} as const;
export type VitalMetric = keyof typeof vitalMetrics;

export function VitalHistory({ patientId }: { patientId: string }) {
  const { interval } = useSync();
  const [metric, setMetric] = useState<VitalMetric>("spo2_pct");
  const query = useQuery({ queryKey: ["history", patientId],
    queryFn: ({ signal }) => fetchHistory(patientId, signal), refetchInterval: interval, retry: false, networkMode: "always" });
  const rows = [...(query.data?.items ?? [])].reverse();
  const [label, unit] = vitalMetrics[metric];
  const points: { time: number; value: number | null }[] = [];
  const measurements: number[] = [];
  rows.forEach((reading, index) => {
    const time = Date.parse(reading.observed_at);
    if (index > 0 && time - Date.parse(rows[index - 1].observed_at) > 10000) {
      points.push({ time: time - 1, value: null });
    }
    const value = reading[metric];
    points.push({ time, value });
    if (value !== null) measurements.push(value);
  });
  return <div className="history">
    <div className="history-controls">
      <label className="field-control">Chart metric <select value={metric} onChange={e => setMetric(e.target.value as VitalMetric)}>
        {Object.entries(vitalMetrics).map(([value, [name, metricUnit]]) =>
          <option key={value} value={value}>{name} ({metricUnit})</option>)}
      </select></label>
      <p>{rows.length} stored readings</p>
    </div>
    {query.isPending && <p className="empty-state" role="status">Loading history…</p>}
    {query.isError && <p role="alert">History refresh failed. Previously fetched history may be outdated.</p>}
    {query.data?.next_cursor && <p>Showing only the newest 2,000 readings in this interval.</p>}
    {!query.isPending && !query.isError && rows.length === 0 && <p className="empty-state">No readings in this interval.</p>}
    {rows.length > 0 && <>
      <p className="chart-summary">{label} · latest stored value <strong>{rows.at(-1)?.[metric] ?? "Missing"}{rows.at(-1)?.[metric] != null ? ` ${unit}` : ""}</strong>.
        {" "}Range {measurements.length ? `${Math.min(...measurements)}–${Math.max(...measurements)} ${unit}` : "unavailable"}.</p>
      {measurements.length > 0 ? <div className="history-chart" role="img" aria-label={`${label} history from stored readings`}>
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={points} margin={{ top: 14, right: 18, bottom: 3, left: 0 }}>
            <defs><linearGradient id="vitals-fill" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-orange)" stopOpacity={0.18}/>
              <stop offset="100%" stopColor="var(--chart-orange)" stopOpacity={0.01}/>
            </linearGradient></defs>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeDasharray="4 4"/>
            <XAxis dataKey="time" type="number" domain={["dataMin", "dataMax"]} minTickGap={35} tickMargin={8}
              tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "var(--chart-grid)" }}
              tickFormatter={v => new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}/>
            <YAxis domain={["auto", "auto"]} width={54} unit={unit} tickMargin={6}
              tick={{ fill: "var(--muted)", fontSize: 11 }} tickLine={false} axisLine={false}/>
            <Tooltip labelFormatter={v => new Date(Number(v)).toLocaleString()} contentStyle={{
              background: "#201a26", border: 0, borderRadius: 8, color: "white", fontSize: 13,
            }} itemStyle={{ color: "white" }}/>
            <Area dataKey="value" type="linear" stroke="none" fill="url(#vitals-fill)" legendType="none"
              tooltipType="none" connectNulls={false} isAnimationActive={false}/>
            <Line dataKey="value" name={label} unit={` ${unit}`} type="linear" stroke="var(--chart-orange)" strokeWidth={2.5}
              dot={measurements.length <= 8 ? { r: 2.5 } : false} connectNulls={false} isAnimationActive={false}/>
          </ComposedChart>
        </ResponsiveContainer>
      </div> : <p className="empty-state">No measurements for this metric in the interval.</p>}
    </>}
    <p className="chart-note">Last 30 minutes by observation time. Missing values and gaps over ten seconds break the line.</p>
  </div>;
}
