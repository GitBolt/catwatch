"use client";

import type { FindingData } from "@/lib/types";
import { SEVERITY_COLORS, ZONE_LABELS, type ZoneId } from "@/lib/constants";

function formatZone(zone: string): string {
  return ZONE_LABELS[zone as ZoneId] || zone.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface Props {
  findings: FindingData[];
  hasMemoryContext?: boolean;
}

export function FindingsList({ findings, hasMemoryContext }: Props) {
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

  const redCount = findings.filter((f) => f.rating === "RED").length;
  const yellowCount = findings.filter((f) => f.rating === "YELLOW").length;
  const greenCount = findings.filter((f) => f.rating === "GREEN").length;

  return (
    <div className="card">
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>Findings</h3>
        {hasMemoryContext && findings.length > 0 && (
          <span style={{
            fontSize: 9,
            fontWeight: 500,
            color: "var(--amber)",
            opacity: 0.6,
            letterSpacing: "0.04em",
          }}>
            Stored to memory
          </span>
        )}
        <div style={{ display: "flex", gap: 6, fontSize: 11, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
          {redCount > 0 && (
            <span style={{ color: SEVERITY_COLORS.RED.text }}>{redCount} RED</span>
          )}
          {yellowCount > 0 && (
            <span style={{ color: SEVERITY_COLORS.YELLOW.text }}>{yellowCount} YEL</span>
          )}
          {greenCount > 0 && (
            <span style={{ color: SEVERITY_COLORS.GREEN.text }}>{greenCount} GRN</span>
          )}
        </div>
      </div>
      <div className="scrollable" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {findings.map((f, i) => {
          const colors = SEVERITY_COLORS[f.rating] || SEVERITY_COLORS.GRAY;
          const zoneLabel = formatZone(f.zone);
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
              {f.snapshot && (
                <img
                  src={`data:image/jpeg;base64,${f.snapshot}`}
                  alt="Evidence"
                  style={{ marginTop: 6, width: "100%", borderRadius: 4, opacity: 0.85 }}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
