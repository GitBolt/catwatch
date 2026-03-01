"use client";

import { useEffect, useState } from "react";

interface Props {
  report: Record<string, unknown> | null;
  onGenerate: () => void;
}

export function ReportDialog({ report, onGenerate }: Props) {
  const [open, setOpen] = useState(false);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    if (report && generating) {
      setGenerating(false);
    }
  }, [report, generating]);

  const handleGenerate = () => {
    setGenerating(true);
    onGenerate();
    setOpen(true);
  };

  return (
    <>
      <button
        onClick={() => {
          if (!report) {
            handleGenerate();
          } else {
            setOpen(true);
          }
        }}
        disabled={generating}
        className="btn btn-secondary"
      >
        {generating ? "Generating..." : report ? "View Report" : "Generate Report"}
      </button>

      {open && (
        <div className="overlay" onClick={() => setOpen(false)}>
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxHeight: "80vh",
              width: "100%",
              maxWidth: 672,
              overflowY: "auto",
              borderRadius: "var(--radius)",
              border: "1px solid var(--border-hover)",
              background: "var(--bg-card)",
              padding: 24,
            }}
          >
            <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 18, fontWeight: 700 }}>Inspection Report</h2>
              <button
                onClick={() => setOpen(false)}
                className="btn btn-secondary btn-small"
              >
                Close
              </button>
            </div>
            {report ? (
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6 }}>
                {typeof report === "string"
                  ? report
                  : JSON.stringify(report, null, 2)}
              </pre>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "24px 0" }}>
                <span className="dot dot-green" />
                <p style={{ fontSize: 14, color: "var(--text-dim)" }}>
                  Generating report — this can take up to 2 minutes...
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
