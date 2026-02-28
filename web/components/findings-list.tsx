"use client";

import type { FindingData } from "@/lib/types";
import { SEVERITY_COLORS, ZONE_LABELS, type ZoneId } from "@/lib/constants";

interface Props {
  findings: FindingData[];
}

export function FindingsList({ findings }: Props) {
  if (findings.length === 0) {
    return (
      <div
        className="card"
        style={{ textAlign: "center", fontSize: 12, color: "var(--text-dim)" }}
      >
        No findings yet
      </div>
    );
  }

  return (
    <div className="card">
      <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 600 }}>Findings</h3>
      <div className="scrollable" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {findings.map((f, i) => {
          const colors = SEVERITY_COLORS[f.rating] || SEVERITY_COLORS.GRAY;
          const zoneLabel =
            ZONE_LABELS[f.zone as ZoneId] || f.zone;
          return (
            <div
              key={i}
              className="finding-row"
              style={{
                borderRadius: "var(--radius)",
                border: `1px solid ${colors.border}`,
                padding: 8,
                background: colors.bg,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: colors.text }}>
                  {f.rating}
                </span>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{zoneLabel}</span>
              </div>
              <p style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>{f.description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
