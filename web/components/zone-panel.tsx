"use client";

import type { EquipmentInfo } from "@/lib/types";

interface Props {
  zonesSeen: Set<string>;
  coverage: number;
  totalZones: number;
  equipmentInfo: EquipmentInfo | null;
  mode: string;
}

function formatZoneName(zone: string): string {
  return zone.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ZonePanel({ zonesSeen, coverage, totalZones, equipmentInfo, mode }: Props) {
  const isCatMode = mode === "cat";

  const dynamicZones = isCatMode ? (equipmentInfo?.inspectable_zones ?? []) : [];
  const allZoneNames = dynamicZones.length > 0
    ? dynamicZones
    : [...zonesSeen];

  const title = isCatMode
    ? (equipmentInfo ? "Checklist" : "Zones")
    : "Areas";

  return (
    <div className="card" style={{ padding: "10px 12px" }}>
      <div style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 12, fontWeight: 600 }}>{title}</h3>
        <span style={{ fontSize: 11, color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>
          {zonesSeen.size}{isCatMode ? `/${totalZones || "?"}` : ""} · {coverage}%
        </span>
      </div>

      {isCatMode && equipmentInfo && (
        <div style={{ marginBottom: 8, fontSize: 11, color: "var(--amber)", fontWeight: 500 }}>
          {equipmentInfo.model_guess || equipmentInfo.equipment_type.replace(/_/g, " ")}
        </div>
      )}

      {allZoneNames.length === 0 && (
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {isCatMode ? "Identifying equipment..." : "Scanning..."}
        </div>
      )}

      {/* General mode: compact chips */}
      {!isCatMode && allZoneNames.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {allZoneNames.map((zone) => (
            <span
              key={zone}
              style={{
                fontSize: 10,
                padding: "2px 7px",
                borderRadius: 4,
                background: "rgba(106, 158, 114, 0.1)",
                border: "1px solid rgba(106, 158, 114, 0.2)",
                color: "var(--text-muted)",
              }}
            >
              {formatZoneName(zone)}
            </span>
          ))}
        </div>
      )}

      {/* CAT mode: checklist rows */}
      {isCatMode && allZoneNames.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {allZoneNames.map((zone) => {
            const seen = zonesSeen.has(zone);
            return (
              <div key={zone} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "1px 0" }}>
                <span className={seen ? "dot dot-green" : "dot dot-gray"} />
                <span style={{ color: seen ? "var(--text)" : "var(--text-dim)" }}>
                  {formatZoneName(zone)}
                </span>
              </div>
            );
          })}

          {dynamicZones.length > 0 && [...zonesSeen].filter((z) => !dynamicZones.includes(z)).length > 0 && (
            <>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4, marginBottom: 1 }}>
                Also detected
              </div>
              {[...zonesSeen]
                .filter((z) => !dynamicZones.includes(z))
                .map((zone) => (
                  <div key={zone} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "1px 0" }}>
                    <span className="dot dot-green" />
                    <span style={{ color: "var(--text)" }}>{formatZoneName(zone)}</span>
                  </div>
                ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
