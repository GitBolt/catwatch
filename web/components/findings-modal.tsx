"use client";

import { useState } from "react";
import { SEVERITY_COLORS, ZONE_LABELS, type ZoneId } from "@/lib/constants";

interface Finding {
  id: string;
  zone: string;
  rating: string;
  description: string;
  createdAt: string;
}

interface Props {
  findings: Finding[];
}

export function FindingsModal({ findings }: Props) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);

  const filtered = filter
    ? findings.filter((f) => f.rating === filter)
    : findings;

  if (findings.length === 0) return null;

  return (
    <>
      <button onClick={() => setOpen(true)} className="btn btn-secondary btn-small">
        View All Findings ({findings.length})
      </button>

      {open && (
        <>
          <div className="modal-backdrop" onClick={() => setOpen(false)} />
          <div className="modal-content" style={{ padding: 0 }}>
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 16, fontWeight: 600 }}>
                Findings ({filtered.length})
              </h2>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ display: "flex", gap: 4 }}>
                  {(["RED", "YELLOW", "GREEN"] as const).map((sev) => {
                    const count = findings.filter((f) => f.rating === sev).length;
                    if (count === 0) return null;
                    const active = filter === sev;
                    const colors = SEVERITY_COLORS[sev];
                    return (
                      <button
                        key={sev}
                        onClick={() => setFilter(active ? null : sev)}
                        style={{
                          padding: "3px 8px",
                          fontSize: 11,
                          fontWeight: 600,
                          borderRadius: 4,
                          background: active ? colors.bg : "transparent",
                          color: active ? colors.text : "var(--text-dim)",
                          border: `1px solid ${active ? colors.border : "var(--border)"}`,
                        }}
                      >
                        {count} {sev.slice(0, 3)}
                      </button>
                    );
                  })}
                </div>
                <button
                  onClick={() => setOpen(false)}
                  style={{ fontSize: 18, color: "var(--text-dim)", lineHeight: 1, padding: "0 4px" }}
                >
                  &times;
                </button>
              </div>
            </div>

            <div style={{ padding: "12px 20px 20px", display: "flex", flexDirection: "column", gap: 8 }}>
              {filtered.map((f) => {
                const sev = f.rating as keyof typeof SEVERITY_COLORS;
                const colors = SEVERITY_COLORS[sev] || SEVERITY_COLORS.GRAY;
                const zoneLabel = ZONE_LABELS[f.zone as ZoneId] || f.zone.replace(/_/g, " ");
                return (
                  <div
                    key={f.id}
                    className="finding-row"
                    style={{
                      borderRadius: 6,
                      borderLeft: `3px solid ${colors.border}`,
                      padding: "10px 12px",
                      background: colors.bg,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: colors.text }}>
                        {f.rating}
                      </span>
                      <span style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 500 }}>
                        {zoneLabel}
                      </span>
                      <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
                        {new Date(f.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>
                    <p style={{ margin: 0, fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
                      {f.description}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </>
  );
}
