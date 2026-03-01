"use client";

import { useEffect, useRef } from "react";
import type { InsightData } from "@/lib/types";
import { SEVERITY_COLORS } from "@/lib/constants";

interface Props {
  insights: InsightData[];
}

const EVENT_LABELS: Record<string, string> = {
  hydraulic_leak: "Hydraulic Leak",
  track_wear: "Track Wear",
  ground_tool_wear: "Tool Wear",
  cab_visibility: "Cab Damage",
  engine_thermal: "Engine Anomaly",
  access_safety: "Access Hazard",
};

export function InsightsPanel({ insights }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [insights.length]);

  if (insights.length === 0) return null;

  return (
    <div className="card">
      <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>
        AI Insights
        <span style={{ fontSize: 11, fontWeight: 400, color: "var(--text-dim)", marginLeft: 8 }}>
          cross-signal
        </span>
      </h3>
      <div className="scrollable" style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 200 }}>
        {insights.map((ins, i) => {
          const colors = SEVERITY_COLORS[ins.vlm_severity] || SEVERITY_COLORS.GRAY;
          return (
            <div
              key={`${ins.event}-${i}`}
              className="finding-row"
              style={{
                borderRadius: "var(--radius)",
                border: `1px solid ${colors.border}`,
                padding: "8px 10px",
                background: colors.bg,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: colors.text }}>
                  {EVENT_LABELS[ins.event] || ins.event}
                </span>
                <span style={{ fontSize: 10, color: "var(--text-dim)" }}>
                  YOLO + VLM
                </span>
              </div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: 0 }}>
                {ins.description}
              </p>
              <div style={{ marginTop: 4, fontSize: 10, color: "var(--text-dim)", display: "flex", gap: 8 }}>
                <span>
                  Components: {ins.components.join(", ")}
                </span>
                <span>
                  Evidence: {ins.evidence_keywords.join(", ")}
                </span>
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
