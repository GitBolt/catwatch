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
        style={{ padding: "10px 12px", textAlign: "center", fontSize: 11, color: "var(--text-dim)" }}
      >
        No findings yet
      </div>
    );
  }

  const redCount = findings.filter((f) => f.rating === "RED").length;
  const yellowCount = findings.filter((f) => f.rating === "YELLOW").length;
  const greenCount = findings.filter((f) => f.rating === "GREEN").length;

  return (
    <div className="card" style={{ padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
        <h3 style={{ fontSize: 12, fontWeight: 600, flex: 1 }}>Findings</h3>
        {hasMemoryContext && findings.length > 0 && (
          <span style={{ fontSize: 8, fontWeight: 500, color: "var(--amber)", opacity: 0.6, letterSpacing: "0.04em" }}>
            Stored to memory
          </span>
        )}
        <div style={{ display: "flex", gap: 5, fontSize: 10, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
          {redCount > 0 && <span style={{ color: SEVERITY_COLORS.RED.text }}>{redCount}R</span>}
          {yellowCount > 0 && <span style={{ color: SEVERITY_COLORS.YELLOW.text }}>{yellowCount}Y</span>}
          {greenCount > 0 && <span style={{ color: SEVERITY_COLORS.GREEN.text }}>{greenCount}G</span>}
        </div>
      </div>
      <div className="scrollable" style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: "40vh" }}>
        {findings.map((f, i) => {
          const colors = SEVERITY_COLORS[f.rating] || SEVERITY_COLORS.GRAY;
          return (
            <div
              key={i}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 6,
                padding: "4px 6px",
                borderRadius: 4,
                borderLeft: `2px solid ${colors.border}`,
                background: colors.bg,
              }}
            >
              <span style={{ fontSize: 9, fontWeight: 700, color: colors.text, flexShrink: 0, marginTop: 1 }}>
                {f.rating === "GREEN" ? "G" : f.rating === "YELLOW" ? "Y" : "R"}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.3 }}>
                {f.description.length > 80 ? f.description.slice(0, 80) + "..." : f.description}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
