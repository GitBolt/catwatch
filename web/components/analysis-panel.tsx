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
            fontSize: 12,
            fontWeight: 700,
            color: colors.text,
          }}
        >
          {sev}
        </span>
        {analysis.callout && (
          <span style={{ fontSize: 14, fontWeight: 500, color: "#ffffff" }}>
            {analysis.callout}
          </span>
        )}
      </div>
      <p style={{ fontSize: 14, color: "#d1d5db" }}>{analysis.description}</p>
      {analysis.findings.length > 0 && (
        <ul style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {analysis.findings.map((f, i) => (
            <li key={i} style={{ fontSize: 12, color: "#9ca3af" }}>
              - {f}
            </li>
          ))}
        </ul>
      )}
      {analysis.zone && (
        <div style={{ marginTop: 8, fontSize: 12, color: "#6b7280" }}>
          Zone: {analysis.zone}
        </div>
      )}
    </div>
  );
}
