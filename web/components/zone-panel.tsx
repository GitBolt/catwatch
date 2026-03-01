"use client";

import type { EquipmentInfo } from "@/lib/types";

interface Props {
  zonesSeen: Set<string>;
  coverage: number;
  totalZones: number;
  equipmentInfo: EquipmentInfo | null;
}

function formatZoneName(zone: string): string {
  return zone.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ZonePanel({ zonesSeen, coverage, totalZones, equipmentInfo }: Props) {
  const dynamicZones = equipmentInfo?.inspectable_zones ?? [];
  const allZoneNames = dynamicZones.length > 0
    ? dynamicZones
    : [...zonesSeen]; // fallback: show only what's been discovered

  return (
    <div className="card">
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 14, fontWeight: 600 }}>
          {equipmentInfo ? "Inspection Checklist" : "Zone Coverage"}
        </h3>
        <span style={{ fontSize: 12, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
          {zonesSeen.size}/{totalZones || "?"} · {coverage}%
        </span>
      </div>

      {equipmentInfo && (
        <div style={{ marginBottom: 10, fontSize: 12, color: "var(--amber)", fontWeight: 500 }}>
          {equipmentInfo.model_guess || equipmentInfo.equipment_type.replace(/_/g, " ")}
          {equipmentInfo.visible_text && (
            <span style={{ color: "var(--text-dim)", fontWeight: 400, marginLeft: 6 }}>
              {equipmentInfo.visible_text}
            </span>
          )}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {allZoneNames.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
            Identifying equipment...
          </div>
        )}
        {allZoneNames.map((zone) => {
          const seen = zonesSeen.has(zone);
          return (
            <div key={zone} className="zone-row" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
              <span className={seen ? "dot dot-green" : "dot dot-gray"} />
              <span style={{ color: seen ? "var(--text)" : "var(--text-dim)" }}>
                {formatZoneName(zone)}
              </span>
            </div>
          );
        })}

        {/* Show any VLM-discovered zones not in the equipment checklist */}
        {dynamicZones.length > 0 && [...zonesSeen].filter((z) => !dynamicZones.includes(z)).length > 0 && (
          <>
            <div style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6, marginBottom: 2 }}>
              Also detected
            </div>
            {[...zonesSeen]
              .filter((z) => !dynamicZones.includes(z))
              .map((zone) => (
                <div key={zone} className="zone-row" style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                  <span className="dot dot-green" />
                  <span style={{ color: "var(--text)" }}>{formatZoneName(zone)}</span>
                </div>
              ))}
          </>
        )}
      </div>
    </div>
  );
}
