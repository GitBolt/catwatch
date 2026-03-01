"use client";

interface Props {
  sessionId: string;
  connected: boolean;
  mode: string;
  yoloMs: number;
  coverage: number;
  totalZones: number;
  onModeChange: (mode: string) => void;
}

export function TopBar({
  sessionId,
  connected,
  mode,
  yoloMs,
  coverage,
  totalZones: _totalZones,
  onModeChange,
}: Props) {
  return (
    <div
      className="card"
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 16px",
        background: "rgba(20, 19, 19, 0.85)",
        backdropFilter: "blur(16px)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="CatWatch" width={28} height={28} style={{ borderRadius: 4 }} />
        </span>
        <span className="mono" style={{ fontSize: 12, color: "var(--text-dim)" }}>
          {sessionId.slice(0, 8)}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <span className={connected ? "dot dot-green" : "dot dot-red"} />
          {connected ? "Live" : "Disconnected"}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 12, color: "var(--text-muted)" }}>
        <span>AI {yoloMs.toFixed(0)}ms</span>
        <span>{coverage} components</span>

        <div
          style={{
            display: "flex",
            borderRadius: 6,
            border: "1px solid var(--border-hover)",
            overflow: "hidden",
          }}
        >
          <button
            onClick={() => onModeChange("general")}
            style={{
              padding: "4px 12px",
              fontSize: 12,
              background: mode === "general" ? "var(--bg-hover)" : "transparent",
              color: mode === "general" ? "var(--text)" : "var(--text-dim)",
            }}
          >
            General
          </button>
          <button
            onClick={() => onModeChange("797")}
            style={{
              padding: "4px 12px",
              fontSize: 12,
              background: mode === "797" ? "var(--amber)" : "transparent",
              color: mode === "797" ? "#1a1714" : "var(--text-dim)",
            }}
          >
            CAT 797F
          </button>
        </div>
      </div>
    </div>
  );
}
