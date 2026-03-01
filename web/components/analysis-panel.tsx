"use client";

import { useEffect, useState } from "react";
import type { AnalysisData } from "@/lib/types";
import { SEVERITY_COLORS } from "@/lib/constants";

interface Props {
  analysis: AnalysisData | null;
}

const ANALYSIS_TTL_MS = 12000;

export function AnalysisPanel({ analysis }: Props) {
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
      <div style={{ marginTop: 8, display: "flex", gap: 12, fontSize: 12, color: "var(--text-dim)" }}>
        {analysis.zone && <span>Zone: {analysis.zone}</span>}
        {typeof analysis.confidence === "number" && (
          <span style={{ opacity: 0.7 }}>
            Confidence: {Math.round(analysis.confidence * 100)}%
          </span>
        )}
      </div>
    </div>
  );
}
