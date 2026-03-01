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
  const trendKey = analysis.component || analysis.zone;
  const trend = trendKey ? zoneTrends[trendKey] : zoneTrends["_global"];

  return (
    <div
      style={{
        borderRadius: "var(--radius)",
        border: `1px solid ${colors.border}`,
        padding: "10px 12px",
        background: colors.bg,
      }}
    >
      {/* Header: severity + callout + memory badge */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: colors.text, letterSpacing: "0.05em" }}>
          {sev}
        </span>
        {analysis.callout && (
          <span style={{ fontSize: 12, fontWeight: 500, color: "var(--text)", flex: 1 }}>
            {analysis.callout}
          </span>
        )}
        {hasMemoryContext && (
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, opacity: 0.6 }}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
        )}
        {typeof analysis.confidence === "number" && (
          <span style={{ fontSize: 10, color: "var(--text-dim)", flexShrink: 0 }}>
            {Math.round(analysis.confidence * 100)}%
          </span>
        )}
      </div>

      {/* Description — truncated */}
      <p style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.4, margin: 0 }}>
        {analysis.description.length > 150 ? analysis.description.slice(0, 150) + "..." : analysis.description}
      </p>

      {/* Trend bar */}
      {trend && trend.sample_count >= 2 && (
        <div
          style={{
            marginTop: 6,
            paddingTop: 5,
            borderTop: "1px solid rgba(255,255,255,0.06)",
            display: "flex",
            alignItems: "center",
            gap: 8,
            fontSize: 10,
            color: "var(--text-dim)",
          }}
        >
          <span>{trend.sample_count}x</span>
          <span style={{ display: "flex", gap: 3, fontVariantNumeric: "tabular-nums" }}>
            {trend.severity_counts.RED > 0 && <span style={{ color: SEVERITY_COLORS.RED.text }}>{trend.severity_counts.RED}R</span>}
            {trend.severity_counts.YELLOW > 0 && <span style={{ color: SEVERITY_COLORS.YELLOW.text }}>{trend.severity_counts.YELLOW}Y</span>}
            {trend.severity_counts.GREEN > 0 && <span style={{ color: SEVERITY_COLORS.GREEN.text }}>{trend.severity_counts.GREEN}G</span>}
          </span>
          <span>{Math.round(trend.confidence_avg * 100)}%</span>
        </div>
      )}
    </div>
  );
}
