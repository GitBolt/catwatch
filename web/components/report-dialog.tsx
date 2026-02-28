"use client";

import { useState } from "react";

interface Props {
  report: Record<string, unknown> | null;
  onGenerate: () => void;
}

export function ReportDialog({ report, onGenerate }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={() => {
          if (!report) onGenerate();
          setOpen(true);
        }}
        className="btn btn-secondary"
      >
        {report ? "View Report" : "Generate Report"}
      </button>

      {open && (
        <div className="overlay">
          <div
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
                style={{ color: "var(--text-muted)" }}
              >
                Close
              </button>
            </div>
            {report ? (
              <pre style={{ whiteSpace: "pre-wrap", fontSize: 14, color: "#d1d5db" }}>
                {typeof report === "string"
                  ? report
                  : JSON.stringify(report, null, 2)}
              </pre>
            ) : (
              <p style={{ fontSize: 14, color: "var(--text-dim)" }}>
                Generating report... this may take a moment.
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}
