"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface DataPoint {
  date: string;
  label: string;
  findings: number;
}

interface Props {
  data: DataPoint[];
}

export function FindingsChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div
        className="card"
        style={{
          padding: 32,
          textAlign: "center",
          color: "var(--text-dim)",
          fontSize: 14,
        }}
      >
        No findings data yet. Run some inspections to see the chart.
      </div>
    );
  }

  return (
    <div
      className="card"
      style={{
        padding: 24,
        height: 280,
      }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "var(--text-dim)" }}
            tickLine={{ stroke: "var(--border)" }}
            axisLine={{ stroke: "var(--border)" }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-dim)" }}
            tickLine={{ stroke: "var(--border)" }}
            axisLine={{ stroke: "var(--border)" }}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius)",
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--text)" }}
            formatter={(value) => [value ?? 0, "Findings"]}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Line
            type="monotone"
            dataKey="findings"
            stroke="var(--amber)"
            strokeWidth={2}
            dot={{ fill: "var(--amber)", strokeWidth: 0, r: 3 }}
            activeDot={{ r: 5, fill: "var(--amber)", stroke: "var(--bg-card)", strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
