"use client";

import type { UnitProfile } from "@/hooks/use-session-socket";
import { SEVERITY_COLORS } from "@/lib/constants";

interface Props {
  unitSerial: string | null;
  unitModel: string | null;
  fleetTag: string | null;
  profile: UnitProfile | null;
  loading: boolean;
}

export function UnitHistoryPanel({ unitSerial, unitModel, fleetTag, profile, loading }: Props) {
  if (!unitSerial) return null;

  return (
    <div
      style={{
        borderRadius: "var(--radius)",
        border: "1px solid var(--border)",
        padding: 16,
        background: "var(--bg-card)",
      }}
    >
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: profile ? "var(--amber)" : "var(--text-dim)",
          }}
        />
        <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
          Unit Memory
        </span>
      </div>

      {/* Unit identity */}
      <div style={{ marginBottom: 12, fontSize: 12, color: "var(--text-dim)" }}>
        <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--amber)" }}>
          {unitSerial}
        </div>
        {unitModel && <div style={{ marginTop: 2 }}>{unitModel}</div>}
        {fleetTag && <div style={{ marginTop: 2 }}>Fleet: {fleetTag}</div>}
      </div>

      {loading && (
        <div style={{ fontSize: 12, color: "var(--text-dim)", fontStyle: "italic" }}>
          Loading unit history...
        </div>
      )}

      {!loading && !profile && (
        <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
          No prior inspection history.
        </div>
      )}

      {profile && (
        <>
          {/* Static profile — long-term facts */}
          {profile.profile.static.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                History
              </div>
              <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {profile.profile.static.map((fact, i) => (
                  <li key={i} style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
                    {fact}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Dynamic profile — recent activity */}
          {profile.profile.dynamic.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Recent
              </div>
              <ul style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {profile.profile.dynamic.map((item, i) => (
                  <li key={i} style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Related findings from past inspections */}
          {profile.searchResults && profile.searchResults.results.length > 0 && (
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-dim)", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Past Findings
              </div>
              <ul style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {profile.searchResults.results.slice(0, 5).map((r) => {
                  const text = r.memory || r.chunk || "";
                  const severityMatch = text.match(/^\[(RED|YELLOW|GREEN)\]/);
                  const severity = severityMatch?.[1] as keyof typeof SEVERITY_COLORS | undefined;
                  const colors = severity ? SEVERITY_COLORS[severity] : null;
                  return (
                    <li
                      key={r.id}
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        lineHeight: 1.4,
                        paddingLeft: 8,
                        borderLeft: colors ? `2px solid ${colors.border}` : "2px solid var(--border)",
                      }}
                    >
                      {text.length > 120 ? text.slice(0, 120) + "..." : text}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
