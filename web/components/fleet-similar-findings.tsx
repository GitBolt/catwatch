"use client";

import { useEffect, useState } from "react";
import { SEVERITY_COLORS } from "@/lib/constants";

interface SearchResult {
  id: string;
  memory?: string;
  chunk?: string;
  similarity: number;
  metadata?: Record<string, unknown>;
}

interface Props {
  unitSerial: string | null;
  findings: { zone: string; rating: string; description: string }[];
}

export function FleetSimilarFindings({ unitSerial, findings }: Props) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    // Build a query from the top findings (RED first, then YELLOW)
    const notable = findings
      .filter((f) => f.rating === "RED" || f.rating === "YELLOW")
      .slice(0, 3);
    if (notable.length === 0) return;

    const query = notable.map((f) => `${f.zone}: ${f.description}`).join(". ");
    if (!query) return;

    setLoading(true);
    // Search across all units (no containerTag = fleet-wide)
    fetch(`/api/memory?action=search&query=${encodeURIComponent(query)}&limit=8`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.results) {
          // Filter out results from the same unit if we know the serial
          const filtered = unitSerial
            ? data.results.filter(
                (r: SearchResult) => r.metadata?.unitSerial !== unitSerial,
              )
            : data.results;
          setResults(filtered);
        }
        setSearched(true);
      })
      .catch(() => setSearched(true))
      .finally(() => setLoading(false));
  }, [findings, unitSerial]);

  if (!searched && !loading) return null;

  return (
    <div>
      <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: 0 }}>
          Similar Findings Across Fleet
        </h2>
        <a
          href="https://supermemory.ai"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: 9,
            fontWeight: 600,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "var(--amber)",
            padding: "3px 8px",
            borderRadius: "var(--radius-sm)",
            border: "1px solid rgba(245, 197, 24, 0.4)",
            background: "rgba(245, 197, 24, 0.08)",
            textDecoration: "none",
            transition: "opacity 0.2s",
          }}
        >
          supermemory
        </a>
      </div>
      {loading && (
        <div className="card" style={{ padding: 24, textAlign: "center", fontSize: 14, color: "var(--text-dim)", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          <span className="pulse" style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--amber)" }} />
          Searching fleet memory...
        </div>
      )}
      {!loading && results.length === 0 && (
        <div className="card" style={{ padding: 24, textAlign: "center", fontSize: 14, color: "var(--text-dim)" }}>
          No similar findings found across other units.
        </div>
      )}
      {!loading && results.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {results.map((r) => {
            const text = r.memory || r.chunk || "";
            const severityMatch = text.match(/^\[(RED|YELLOW|GREEN)\]/);
            const severity = severityMatch?.[1] as keyof typeof SEVERITY_COLORS | undefined;
            const colors = severity ? SEVERITY_COLORS[severity] : SEVERITY_COLORS.GRAY;
            const similarity = Math.round(r.similarity * 100);
            return (
              <div
                key={r.id}
                style={{
                  borderRadius: "var(--radius)",
                  border: `1px solid ${colors.border}`,
                  padding: 16,
                  background: colors.bg,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  {severity && (
                    <span style={{ fontSize: 12, fontWeight: 700, color: colors.text }}>
                      {severity}
                    </span>
                  )}
                  <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-dim)" }}>
                    {similarity}% match
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--text-muted)", lineHeight: 1.5 }}>
                  {text.replace(/^\[(RED|YELLOW|GREEN)\]\s*/, "").slice(0, 200)}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
