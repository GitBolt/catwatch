"use client";

import Image from "next/image";
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
      {/* Top row: identity + status */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v6l4 2" />
        </svg>
        <span className="mono" style={{ fontSize: 11, fontWeight: 600, color: "var(--amber)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
          {label}
        </span>
        {unitModel && (
          <span style={{ fontSize: 10, color: "var(--text-dim)", flexShrink: 0 }}>{unitModel}</span>
        )}
      </div>

      {/* Status line */}
      <div style={{ fontSize: 10, color: "var(--text-dim)", display: "flex", alignItems: "center", gap: 5, marginBottom: 6 }}>
        {loading && (
          <>
            <span className="pulse" style={{ display: "inline-block", width: 4, height: 4, borderRadius: "50%", background: "var(--amber)", flexShrink: 0 }} />
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
            <span style={{ display: "inline-block", width: 4, height: 4, borderRadius: "50%", background: "var(--amber)", flexShrink: 0 }} />
            <span style={{ color: "var(--amber)", fontWeight: 500 }}>
              Comparing against {pastCount > 0 ? `${pastCount} past finding${pastCount !== 1 ? "s" : ""}` : `${factCount} note${factCount !== 1 ? "s" : ""}`}
            </span>
          </>
        )}
      </div>

      <a
        href="https://supermemory.ai"
        target="_blank"
        rel="noopener noreferrer"
        style={{ display: "flex", alignItems: "center", gap: 5, textDecoration: "none", opacity: 0.7, transition: "opacity 0.2s" }}
        onMouseEnter={(e) => { e.currentTarget.style.opacity = "1"; }}
        onMouseLeave={(e) => { e.currentTarget.style.opacity = "0.7"; }}
      >
        <Image
          src="/supermemory.png"
          alt="Supermemory"
          width={13}
          height={13}
          style={{ borderRadius: 2, filter: "brightness(1.8)" }}
        />
        <span style={{ fontSize: 9, color: "var(--text-muted)", letterSpacing: "0.02em" }}>
          Powered by Supermemory
        </span>
      </a>
    </div>
  );
}
