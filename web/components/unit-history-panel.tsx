"use client";

import type { UnitProfile } from "@/hooks/use-session-socket";

interface Props {
  unitSerial: string | null;
  unitModel: string | null;
  fleetTag: string | null;
  location: string | null;
  memoryKey: string | null;
  profile: UnitProfile | null;
  loading: boolean;
}

export function UnitHistoryPanel({ unitSerial, unitModel, fleetTag, location, memoryKey, profile, loading }: Props) {
  if (!memoryKey) return null;

  const isGeo = memoryKey.startsWith("geo:");

  let label = memoryKey;
  if (unitSerial) {
    label = unitSerial;
  } else if (location) {
    label = location;
  } else if (isGeo) {
    label = `Near ${memoryKey.replace("geo:", "")}`;
  }

  const pastCount = profile?.searchResults?.results.length ?? 0;
  const factCount = (profile?.profile.static.length ?? 0) + (profile?.profile.dynamic.length ?? 0);
  const hasHistory = pastCount > 0 || factCount > 0;

  return (
    <div
      style={{
        borderRadius: "var(--radius)",
        border: hasHistory ? "1px solid rgba(196, 162, 76, 0.3)" : "1px solid var(--border)",
        padding: "8px 12px",
        background: hasHistory ? "rgba(196, 162, 76, 0.03)" : "var(--bg-card)",
        transition: "border-color 0.3s ease",
      }}
    >
      {/* Top row: identity + supermemory badge */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }}>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <circle cx="12" cy="12" r="10" />
            <path d="M12 6v6l4 2" />
          </svg>
          <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--amber)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {label}
          </span>
          {unitModel && (
            <span style={{ fontSize: 11, color: "var(--text-dim)", flexShrink: 0 }}>{unitModel}</span>
          )}
        </div>
        <span style={{ fontSize: 8, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--amber)", opacity: 0.5, flexShrink: 0 }}>
          supermemory
        </span>
      </div>

      {/* Status line */}
      <div style={{ marginTop: 4, fontSize: 11, color: "var(--text-dim)", display: "flex", alignItems: "center", gap: 6 }}>
        {loading && (
          <>
            <span className="pulse" style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "var(--amber)", flexShrink: 0 }} />
            <span>Searching memory...</span>
          </>
        )}
        {!loading && !profile && (
          <span>First inspection — building memory</span>
        )}
        {!loading && profile && !hasHistory && (
          <span>Memory connected · no prior findings</span>
        )}
        {!loading && hasHistory && (
          <>
            <span style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "var(--amber)", flexShrink: 0 }} />
            <span style={{ color: "var(--amber)", fontWeight: 500 }}>
              Comparing against {pastCount > 0 ? `${pastCount} past finding${pastCount !== 1 ? "s" : ""}` : `${factCount} memory note${factCount !== 1 ? "s" : ""}`}
            </span>
          </>
        )}
      </div>
    </div>
  );
}
