"use client";

import { useEffect, useRef } from "react";
import type { InsightData } from "@/lib/types";
import { SEVERITY_COLORS } from "@/lib/constants";

interface Props {
  insights: InsightData[];
}

const EVENT_LABELS: Record<string, string> = {
  hydraulic_leak: "Hydraulic Leak",
  tire_damage: "Tire Damage",
  dump_body_wear: "Body Damage",
  suspension_issue: "Suspension",
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
    <div className="card" style={{ padding: "10px 12px" }}>
      <h3 style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>
        Insights
        <span style={{ fontSize: 10, fontWeight: 400, color: "var(--text-dim)", marginLeft: 6 }}>
          YOLO+VLM
        </span>
      </h3>
      <div className="scrollable" style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 160 }}>
        {insights.map((ins, i) => {
          const colors = SEVERITY_COLORS[ins.vlm_severity] || SEVERITY_COLORS.GRAY;
          return (
            <div
              key={`${ins.event}-${i}`}
              style={{
                padding: "4px 6px",
                borderRadius: 4,
                borderLeft: `2px solid ${colors.border}`,
                background: colors.bg,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: colors.text }}>
                  {EVENT_LABELS[ins.event] || ins.event}
                </span>
              </div>
              <p style={{ fontSize: 11, color: "var(--text-muted)", margin: 0, lineHeight: 1.3 }}>
                {ins.description.length > 100 ? ins.description.slice(0, 100) + "..." : ins.description}
              </p>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
