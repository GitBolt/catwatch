"use client";

import { ALL_ZONES, ZONE_LABELS } from "@/lib/constants";

interface Props {
  zonesSeen: Set<string>;
  coverage: number;
}

export function ZonePanel({ zonesSeen, coverage }: Props) {
  return (
    <div className="card">
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 14, fontWeight: 600 }}>Zone Coverage</h3>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {zonesSeen.size}/{ALL_ZONES.length} · {coverage}%
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {ALL_ZONES.map((zone) => {
          const seen = zonesSeen.has(zone);
          return (
            <div key={zone} className="zone-row" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
              <span
                className={seen ? "dot dot-green" : "dot dot-gray"}
              />
              <span style={{ color: seen ? "var(--text)" : "var(--text-dim)" }}>
                {ZONE_LABELS[zone]}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
