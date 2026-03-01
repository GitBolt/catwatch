"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  generateInspectionPDF,
  type InspectionPDFData,
} from "@/lib/generate-pdf";

interface Props {
  inspection: InspectionPDFData;
}

export function ReportPreview({ inspection }: Props) {
  const [pages, setPages] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const rendered = useRef(false);

  useEffect(() => {
    if (rendered.current) return;
    rendered.current = true;

    async function render() {
      try {
        const doc = generateInspectionPDF(inspection);
        const arrayBuffer = doc.output("arraybuffer");

        const pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjsLib.version}/build/pdf.worker.min.mjs`;

        const pdf = await pdfjsLib.getDocument({ data: new Uint8Array(arrayBuffer) }).promise;
        const images: string[] = [];

        for (let i = 1; i <= pdf.numPages; i++) {
          const page = await pdf.getPage(i);
          const viewport = page.getViewport({ scale: 2 });

          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          const ctx = canvas.getContext("2d")!;

          await page.render({ canvasContext: ctx, viewport, canvas }).promise;
          images.push(canvas.toDataURL("image/png"));
        }

        setPages(images);
      } catch (err) {
        console.error("PDF render failed:", err);
        setError("Failed to render report preview.");
      } finally {
        setLoading(false);
      }
    }

    render();
  }, [inspection]);

  const download = useCallback(() => {
    try {
      const doc = generateInspectionPDF(inspection);
      doc.save(`catwatch-inspection-${inspection.sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      console.error("PDF download failed:", err);
    }
  }, [inspection]);

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ fontSize: 18, fontWeight: 600 }}>Report</h2>
        <button onClick={download} className="btn btn-primary" style={{ gap: 6 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Download PDF
        </button>
      </div>

      {loading && (
        <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--text-dim)", fontSize: 14 }}>
          Generating report...
        </div>
      )}

      {error && (
        <div className="card" style={{ padding: 24, textAlign: "center", color: "var(--red)", fontSize: 14 }}>
          {error}
        </div>
      )}

      {pages.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {pages.map((dataUrl, i) => (
            <img
              key={i}
              src={dataUrl}
              alt={`Report page ${i + 1}`}
              style={{
                width: "100%",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
                boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
