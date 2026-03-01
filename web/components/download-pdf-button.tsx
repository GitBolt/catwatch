"use client";

import { useState } from "react";
import {
    generateInspectionPDF,
    type InspectionPDFData,
} from "@/lib/generate-pdf";

interface Props {
    inspection: InspectionPDFData;
}

export function DownloadPDFButton({ inspection }: Props) {
    const [generating, setGenerating] = useState(false);

    async function handleClick() {
        setGenerating(true);
        try {
            const doc = await generateInspectionPDF(inspection);
            doc.save(
                `catwatch-inspection-${inspection.sessionId.slice(0, 8)}.pdf`
            );
        } catch (err) {
            console.error("PDF generation failed:", err);
        } finally {
            setGenerating(false);
        }
    }

    return (
        <button
            onClick={handleClick}
            disabled={generating}
            className="btn btn-primary"
            style={{ gap: 6 }}
        >
            <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
            >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            {generating ? "Generating..." : "Download PDF"}
        </button>
    );
}
