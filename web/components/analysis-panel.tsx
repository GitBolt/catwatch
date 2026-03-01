"use client";

import { useEffect, useState } from "react";
import type { AnalysisData, ZoneTrend } from "@/lib/types";
import { SEVERITY_COLORS } from "@/lib/constants";

interface Props {
  analysis: AnalysisData | null;
  zoneTrends: Record<string, ZoneTrend>;
  hasMemoryContext?: boolean;
}

const ANALYSIS_TTL_MS = 12000;

const DRIFT_LABELS: Record<string, { label: string; color: string }> = {
  worsening: { label: "worsening", color: "var(--red, #b85c5c)" },
  improving: { label: "improving", color: "#82b88a" },
  stable: { label: "stable", color: "var(--text-dim)" },
  inconsistent: { label: "inconsistent", color: "var(--amber, #b09340)" },
};

export function AnalysisPanel({ analysis, zoneTrends, hasMemoryContext }: Props) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (analysis) {
      setVisible(true);
      const timer = setTimeout(() => setVisible(false), ANALYSIS_TTL_MS);
      return () => clearTimeout(timer);
    }
  }, [analysis]);

  if (!analysis || !visible) return null;

  const sev = analysis.severity || "GREEN";
  const colors = SEVERITY_COLORS[sev] || SEVERITY_COLORS.GRAY;
  const trend = analysis.zone ? zoneTrends[analysis.zone] : zoneTrends["_global"];

  return (
    <div
      style={{
        borderRadius: "var(--radius)",
        border: `1px solid ${colors.border}`,
        padding: 16,
        background: colors.bg,
      }}
    >
      <div style={{ marginBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            display: "inline-block",
            borderRadius: 4,
            padding: "2px 8px",
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.05em",
            textTransform: "uppercase" as const,
            color: colors.text,
          }}
        >
          {sev}
        </span>
        {analysis.callout && (
          <span style={{ fontSize: 14, fontWeight: 500, color: "var(--text)" }}>
            {analysis.callout}
          </span>
        )}
      </div>
      {hasMemoryContext && (
        <div style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          marginBottom: 6,
          padding: "2px 8px",
          borderRadius: "var(--radius-sm)",
          background: "rgba(196, 162, 76, 0.08)",
          border: "1px solid rgba(196, 162, 76, 0.15)",
        }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <span style={{ fontSize: 10, fontWeight: 500, color: "var(--amber)", letterSpacing: "0.02em" }}>
            Compared against prior inspections
          </span>
        </div>
      )}
      <p style={{ fontSize: 13, color: "var(--text-muted)" }}>{analysis.description}</p>
      {analysis.findings.length > 0 && (
        <ul style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {analysis.findings.map((f, i) => (
            <li key={i} style={{ fontSize: 12, color: "var(--text-muted)" }}>
              - {f}
            </li>
          ))}
        </ul>
      )}

      <div style={{ marginTop: 8, display: "flex", gap: 12, fontSize: 12, color: "var(--text-dim)", flexWrap: "wrap" }}>
        {analysis.zone && <span>Zone: {analysis.zone}</span>}
        {typeof analysis.confidence === "number" && (
          <span style={{ opacity: 0.7 }}>
            Confidence: {Math.round(analysis.confidence * 100)}%
          </span>
        )}
      </div>

      {trend && trend.sample_count >= 2 && (
        <div
          style={{
            marginTop: 10,
            paddingTop: 8,
            borderTop: "1px solid rgba(255,255,255,0.06)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            fontSize: 11,
          }}
        >
          <span style={{ color: "var(--text-dim)" }}>
            {trend.sample_count} analyses
          </span>
          <span style={{ display: "flex", gap: 4, fontVariantNumeric: "tabular-nums" }}>
            {trend.severity_counts.RED > 0 && (
              <span style={{ color: SEVERITY_COLORS.RED.text }}>
                {trend.severity_counts.RED}R
              </span>
            )}
            {trend.severity_counts.YELLOW > 0 && (
              <span style={{ color: SEVERITY_COLORS.YELLOW.text }}>
                {trend.severity_counts.YELLOW}Y
              </span>
            )}
            {trend.severity_counts.GREEN > 0 && (
              <span style={{ color: SEVERITY_COLORS.GREEN.text }}>
                {trend.severity_counts.GREEN}G
              </span>
            )}
          </span>
          <span style={{ color: "var(--text-dim)" }}>
            {Math.round(trend.confidence_avg * 100)}% avg
          </span>
          <span style={{ color: DRIFT_LABELS[trend.drift]?.color ?? "var(--text-dim)", fontWeight: 600 }}>
            {DRIFT_LABELS[trend.drift]?.label ?? trend.drift}
          </span>
        </div>
      )}
    </div>
  );
}
