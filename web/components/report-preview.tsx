"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  generateInspectionPDF,
  type InspectionPDFData,
} from "@/lib/generate-pdf";

interface Props {
  inspection: InspectionPDFData;
}

type ViewMode = "pdf" | "json";

export function ReportPreview({ inspection }: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("pdf");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    try {
      const doc = generateInspectionPDF(inspection);
      const blob = doc.output("blob");
      const url = URL.createObjectURL(blob);
      setPdfUrl(url);
      return () => URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF generation failed:", err);
      setError("Failed to generate PDF.");
    }
  }, [inspection]);

  const download = useCallback(() => {
    try {
      const doc = generateInspectionPDF(inspection);
      doc.save(`catwatch-inspection-${inspection.sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error("PDF download failed:", err);
    }
  }, [inspection]);

  const jsonString = useMemo(() => {
    const obj: Record<string, unknown> = {
      session_id: inspection.sessionId,
      mode: inspection.mode,
      status: inspection.status,
      created_at: inspection.createdAt,
      ended_at: inspection.endedAt,
      coverage_pct: inspection.coveragePct,
      zones_seen: inspection.zonesSeen,
      findings: inspection.findings,
    };
    if (inspection.report?.data) {
      obj.report = inspection.report.data;
    }
    return JSON.stringify(obj, null, 2);
  }, [inspection]);

  const copyJson = useCallback(() => {
    navigator.clipboard.writeText(jsonString).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [jsonString]);

  const downloadJson = useCallback(() => {
    const blob = new Blob([jsonString], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `catwatch-inspection-${inspection.sessionId.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [jsonString, inspection.sessionId]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>Report</h2>
          <div style={{ display: "flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border)" }}>
            <button
              onClick={() => setViewMode("pdf")}
              style={{
                padding: "4px 12px",
                fontSize: 12,
                fontWeight: 500,
                border: "none",
                cursor: "pointer",
                background: viewMode === "pdf" ? "var(--amber)" : "transparent",
                color: viewMode === "pdf" ? "#000" : "var(--text-muted)",
              }}
            >
              PDF
            </button>
            <button
              onClick={() => setViewMode("json")}
              style={{
                padding: "4px 12px",
                fontSize: 12,
                fontWeight: 500,
                border: "none",
                borderLeft: "1px solid var(--border)",
                cursor: "pointer",
                background: viewMode === "json" ? "var(--amber)" : "transparent",
                color: viewMode === "json" ? "#000" : "var(--text-muted)",
              }}
            >
              JSON
            </button>
          </div>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          {viewMode === "json" && (
            <>
              <button onClick={copyJson} className="btn" style={{ gap: 6, fontSize: 12 }}>
                {copied ? "Copied" : "Copy"}
              </button>
              <button onClick={downloadJson} className="btn" style={{ gap: 6, fontSize: 12 }}>
                Download .json
              </button>
            </>
          )}
          <button onClick={download} className="btn btn-primary" style={{ gap: 6 }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="card" style={{ padding: 24, textAlign: "center", color: "var(--red)", fontSize: 14 }}>
          {error}
        </div>
      )}

      {viewMode === "pdf" && (
        <>
          {!pdfUrl && !error && (
            <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--text-dim)", fontSize: 14 }}>
              Generating report...
            </div>
          )}
          {pdfUrl && (
            <iframe
              src={pdfUrl}
              title="Inspection Report PDF"
              style={{
                width: "100%",
                height: "80vh",
                minHeight: 600,
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
                background: "#fff",
              }}
            />
          )}
        </>
      )}

      {viewMode === "json" && (
        <div
          className="card"
          style={{
            padding: 16,
            maxHeight: "80vh",
            overflow: "auto",
          }}
        >
          <pre
            style={{
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--text-muted)",
              fontFamily: "var(--font-mono, monospace)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              margin: 0,
            }}
          >
            {jsonString}
          </pre>
        </div>
      )}
    </div>
  );
}
