"use client";

import type { EquipmentInfo } from "@/lib/types";

interface Props {
  componentsSeen: Set<string>;
  coverage: number;
  equipmentInfo: EquipmentInfo | null;
  mode: string;
}

function formatName(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function InspectionChecklist({ componentsSeen, coverage, equipmentInfo, mode }: Props) {
  const isCatMode = mode === "797";

  const expected = isCatMode ? (equipmentInfo?.inspectable_zones ?? []) : [];
  const allNames = expected.length > 0 ? expected : [...componentsSeen];

  const title = isCatMode
    ? (equipmentInfo ? "Checklist" : "Components")
    : "Areas Detected";

  return (
    <div className="card" style={{ padding: "10px 12px" }}>
      <div style={{ marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ fontSize: 12, fontWeight: 600 }}>{title}</h3>
        <span style={{ fontSize: 11, color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>
          {componentsSeen.size} · {coverage}%
        </span>
      </div>

      {isCatMode && equipmentInfo && (
        <div style={{ marginBottom: 8, fontSize: 11, color: "var(--amber)", fontWeight: 500 }}>
          {equipmentInfo.model_guess || equipmentInfo.equipment_type.replace(/_/g, " ")}
        </div>
      )}

      {allNames.length === 0 && (
        <div style={{ fontSize: 11, color: "var(--text-dim)" }}>
          {isCatMode ? "Identifying equipment..." : "Scanning..."}
        </div>
      )}

      {!isCatMode && allNames.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          {allNames.map((name) => (
            <span
              key={name}
              style={{
                fontSize: 10,
                padding: "2px 7px",
                borderRadius: 4,
                background: "rgba(106, 158, 114, 0.1)",
                border: "1px solid rgba(106, 158, 114, 0.2)",
                color: "var(--text-muted)",
              }}
            >
              {formatName(name)}
            </span>
          ))}
        </div>
      )}

      {isCatMode && allNames.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {allNames.map((name) => {
            const seen = componentsSeen.has(name);
            return (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "1px 0" }}>
                <span className={seen ? "dot dot-green" : "dot dot-gray"} />
                <span style={{ color: seen ? "var(--text)" : "var(--text-dim)" }}>
                  {formatName(name)}
                </span>
              </div>
            );
          })}

          {expected.length > 0 && [...componentsSeen].filter((c) => !expected.includes(c)).length > 0 && (
            <>
              <div style={{ fontSize: 10, color: "var(--text-dim)", marginTop: 4, marginBottom: 1 }}>
                Also detected
              </div>
              {[...componentsSeen]
                .filter((c) => !expected.includes(c))
                .map((name) => (
                  <div key={name} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, padding: "1px 0" }}>
                    <span className="dot dot-green" />
                    <span style={{ color: "var(--text)" }}>{formatName(name)}</span>
                  </div>
                ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
