import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import { ZONE_LABELS, type ZoneId } from "./constants";

/* ─── Types ──────────────────────────────────────────────────── */

export interface InspectionPDFData {
  sessionId: string;
  mode: string;
  status: string;
  createdAt: string;
  endedAt: string | null;
  coveragePct: number;
  zonesSeen: number;
  findings: {
    zone: string;
    rating: string;
    description: string;
    createdAt: string;
  }[];
  report?: {
    data: unknown;
  } | null;
}

/* ─── Color Palette (matching CAT branding) ──────────────────── */

const AMBER = [245, 197, 24] as const;
const BLACK = [0, 0, 0] as const;
const WHITE = [255, 255, 255] as const;
const DARK_GRAY = [60, 60, 60] as const;
const MID_GRAY = [128, 128, 128] as const;
const LIGHT_GRAY = [240, 240, 240] as const;
const TABLE_BORDER = [180, 180, 180] as const;
const GREEN_BG = [220, 245, 220] as const;
const YELLOW_BG = [255, 248, 210] as const;
const RED_BG = [255, 220, 220] as const;
const GREEN_TEXT = [34, 120, 34] as const;
const YELLOW_TEXT = [150, 120, 0] as const;
const RED_TEXT = [180, 40, 40] as const;

/* ─── Helpers ────────────────────────────────────────────────── */

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-US", {
    month: "numeric",
    day: "numeric",
    year: "numeric",
  });
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getRatingColor(rating: string): {
  bg: readonly [number, number, number];
  text: readonly [number, number, number];
} {
  switch (rating.toUpperCase()) {
    case "GREEN":
      return { bg: GREEN_BG, text: GREEN_TEXT };
    case "YELLOW":
      return { bg: YELLOW_BG, text: YELLOW_TEXT };
    case "RED":
      return { bg: RED_BG, text: RED_TEXT };
    default:
      return { bg: LIGHT_GRAY, text: DARK_GRAY };
  }
}

function getExpirationDate(createdDateStr: string): string {
  const d = new Date(createdDateStr);
  d.setMonth(d.getMonth() + 2);
  return formatDate(d.toISOString());
}

function getDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const mins = Math.round(ms / 60000);
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

/* ─── Main PDF Generator ─────────────────────────────────────── */

export function generateInspectionPDF(data: InspectionPDFData): jsPDF {
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 14;
  const contentWidth = pageWidth - margin * 2;
  let y = 12;

  // ── Header Band ────────────────────────────────────────────
  doc.setFillColor(...AMBER);
  doc.rect(0, 0, pageWidth, 28, "F");

  // Logo text "CATWATCH" in header
  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(...BLACK);
  doc.text("CATWATCH", margin, 18);

  // Title
  doc.setFontSize(14);
  doc.setTextColor(...BLACK);
  doc.text("Equipment Inspection Report", pageWidth - margin, 12, {
    align: "right",
  });

  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.text("Drone-Based Automated Inspection", pageWidth - margin, 18, {
    align: "right",
  });

  doc.setFontSize(8);
  doc.setTextColor(...DARK_GRAY);
  doc.text(`Report ID: ${data.sessionId.slice(0, 12)}`, pageWidth - margin, 24, {
    align: "right",
  });

  y = 34;

  // ── Appraisal Family Header ────────────────────────────────
  doc.setFillColor(...BLACK);
  doc.rect(margin, y, contentWidth, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...WHITE);
  doc.text(
    `  INSPECTION SESSION: ${data.mode.toUpperCase()} MODE`,
    margin + 2,
    y + 5
  );
  y += 10;

  // ── Session Info Table ─────────────────────────────────────
  const sessionInfoRows = [
    ["Session ID", data.sessionId],
    ["Inspection Date", formatDate(data.createdAt)],
    [
      "Inspection Time",
      formatTime(data.createdAt),
    ],
    ["Status", data.status.charAt(0).toUpperCase() + data.status.slice(1)],
    ["Duration", getDuration(data.createdAt, data.endedAt)],
    [
      "Expiration Date",
      getExpirationDate(data.createdAt),
    ],
  ];

  autoTable(doc, {
    startY: y,
    head: [],
    body: sessionInfoRows,
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: {
      fontSize: 8,
      cellPadding: 2,
      lineColor: [...TABLE_BORDER],
      lineWidth: 0.3,
    },
    columnStyles: {
      0: {
        fontStyle: "bold",
        cellWidth: 40,
        fillColor: [...LIGHT_GRAY],
        textColor: [...DARK_GRAY],
      },
      1: { textColor: [...BLACK] },
    },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── Coverage Configuration ─────────────────────────────────
  doc.setFillColor(...BLACK);
  doc.rect(margin, y, contentWidth, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...WHITE);
  doc.text("  COVERAGE CONFIGURATION", margin + 2, y + 5);
  y += 10;

  const coverageRows = [
    ["Mode", data.mode.toUpperCase()],
    ["Coverage", `${Math.round(data.coveragePct)}%`],
    ["Zones Inspected", `${data.zonesSeen} / 15`],
    [
      "Findings Count",
      `${data.findings.length}`,
    ],
    [
      "Red Flags",
      `${data.findings.filter((f) => f.rating === "RED").length}`,
    ],
    [
      "Yellow Flags",
      `${data.findings.filter((f) => f.rating === "YELLOW").length}`,
    ],
    [
      "Green Items",
      `${data.findings.filter((f) => f.rating === "GREEN").length}`,
    ],
  ];

  autoTable(doc, {
    startY: y,
    head: [],
    body: coverageRows,
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: {
      fontSize: 8,
      cellPadding: 2,
      lineColor: [...TABLE_BORDER],
      lineWidth: 0.3,
    },
    columnStyles: {
      0: {
        fontStyle: "bold",
        cellWidth: 40,
        fillColor: [...LIGHT_GRAY],
        textColor: [...DARK_GRAY],
      },
      1: { textColor: [...BLACK] },
    },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── General Appearance (Findings Table) ───────────────────
  doc.setFillColor(...BLACK);
  doc.rect(margin, y, contentWidth, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...WHITE);
  doc.text("  GENERAL APPEARANCE", margin + 2, y + 5);
  y += 10;

  // Build zone-based findings summary
  const ALL_ZONE_KEYS = Object.keys(ZONE_LABELS) as ZoneId[];
  const zoneFindingsMap = new Map<
    string,
    { rating: string; description: string }[]
  >();

  data.findings.forEach((f) => {
    const existing = zoneFindingsMap.get(f.zone) || [];
    existing.push({ rating: f.rating, description: f.description });
    zoneFindingsMap.set(f.zone, existing);
  });

  const appearanceRows: any[][] = [];

  ALL_ZONE_KEYS.forEach((zoneKey) => {
    const label = ZONE_LABELS[zoneKey];
    const findings = zoneFindingsMap.get(zoneKey);

    if (findings && findings.length > 0) {
      const worstRating = findings.reduce((worst, f) => {
        const order: Record<string, number> = {
          RED: 3,
          YELLOW: 2,
          GREEN: 1,
        };
        return (order[f.rating] || 0) > (order[worst] || 0)
          ? f.rating
          : worst;
      }, findings[0].rating);

      const colors = getRatingColor(worstRating);
      const descriptions = findings
        .map((f) => f.description)
        .join("; ")
        .toUpperCase();

      appearanceRows.push([
        { content: label, styles: { fontStyle: "bold" as const } },
        {
          content: worstRating,
          styles: {
            fillColor: [...colors.bg],
            textColor: [...colors.text],
            fontStyle: "bold" as const,
          },
        },
        { content: descriptions, styles: {} },
      ]);
    } else {
      appearanceRows.push([
        { content: label, styles: { fontStyle: "bold" as const } },
        {
          content: "Good",
          styles: {
            fillColor: [...GREEN_BG],
            textColor: [...GREEN_TEXT],
            fontStyle: "bold",
          },
        },
        { content: "", styles: {} },
      ]);
    }
  });

  autoTable(doc, {
    startY: y,
    head: [
      [
        {
          content: "Zone",
          styles: {
            fillColor: [...LIGHT_GRAY],
            textColor: [...DARK_GRAY],
            fontStyle: "bold",
          },
        },
        {
          content: "CODE",
          styles: {
            fillColor: [...LIGHT_GRAY],
            textColor: [...DARK_GRAY],
            fontStyle: "bold",
          },
        },
        {
          content: "REMARKS",
          styles: {
            fillColor: [...LIGHT_GRAY],
            textColor: [...DARK_GRAY],
            fontStyle: "bold",
          },
        },
      ],
    ],
    body: appearanceRows,
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: {
      fontSize: 8,
      cellPadding: 2.5,
      lineColor: [...TABLE_BORDER],
      lineWidth: 0.3,
      textColor: [...BLACK],
    },
    columnStyles: {
      0: { cellWidth: 40 },
      1: { cellWidth: 20, halign: "center" },
      2: {},
    },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── Detailed Findings Log ──────────────────────────────────
  if (data.findings.length > 0) {
    // Check if we need a new page
    if (y > 240) {
      doc.addPage();
      y = 14;
    }

    doc.setFillColor(...BLACK);
    doc.rect(margin, y, contentWidth, 7, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...WHITE);
    doc.text("  DETAILED FINDINGS LOG", margin + 2, y + 5);
    y += 10;

    const detailedRows: any[][] = data.findings.map((f) => {
      const zoneLabel =
        ZONE_LABELS[f.zone as ZoneId] || f.zone;
      const colors = getRatingColor(f.rating);
      return [
        formatTime(f.createdAt),
        { content: zoneLabel, styles: { fontStyle: "bold" as const } },
        {
          content: f.rating,
          styles: {
            fillColor: [...colors.bg] as [number, number, number],
            textColor: [...colors.text] as [number, number, number],
            fontStyle: "bold" as const,
            halign: "center" as const,
          },
        },
        f.description,
      ];
    });

    autoTable(doc, {
      startY: y,
      head: [
        [
          {
            content: "Time",
            styles: {
              fillColor: [...LIGHT_GRAY],
              textColor: [...DARK_GRAY],
              fontStyle: "bold",
            },
          },
          {
            content: "Zone",
            styles: {
              fillColor: [...LIGHT_GRAY],
              textColor: [...DARK_GRAY],
              fontStyle: "bold",
            },
          },
          {
            content: "Rating",
            styles: {
              fillColor: [...LIGHT_GRAY],
              textColor: [...DARK_GRAY],
              fontStyle: "bold",
            },
          },
          {
            content: "Description",
            styles: {
              fillColor: [...LIGHT_GRAY],
              textColor: [...DARK_GRAY],
              fontStyle: "bold",
            },
          },
        ],
      ],
      body: detailedRows,
      theme: "grid",
      margin: { left: margin, right: margin },
      styles: {
        fontSize: 7.5,
        cellPadding: 2,
        lineColor: [...TABLE_BORDER],
        lineWidth: 0.3,
        textColor: [...BLACK],
      },
      columnStyles: {
        0: { cellWidth: 22 },
        1: { cellWidth: 32 },
        2: { cellWidth: 18, halign: "center" },
        3: {},
      },
    });

    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ── Report Summary (if available) ─────────────────────────
  if (data.report) {
    if (y > 220) {
      doc.addPage();
      y = 14;
    }

    doc.setFillColor(...BLACK);
    doc.rect(margin, y, contentWidth, 7, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...WHITE);
    doc.text("  AI ANALYSIS REPORT", margin + 2, y + 5);
    y += 10;

    const reportText =
      typeof data.report.data === "string"
        ? data.report.data
        : JSON.stringify(data.report.data, null, 2);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...DARK_GRAY);

    const lines = doc.splitTextToSize(reportText, contentWidth - 8);
    const lineHeight = 3.5;

    // Draw a bordered background
    const boxHeight = Math.min(lines.length * lineHeight + 8, 200);
    doc.setDrawColor(...TABLE_BORDER);
    doc.setLineWidth(0.3);
    doc.rect(margin, y, contentWidth, boxHeight);

    let textY = y + 5;
    for (const line of lines) {
      if (textY > doc.internal.pageSize.getHeight() - 20) {
        doc.addPage();
        textY = 14;
      }
      doc.text(line, margin + 4, textY);
      textY += lineHeight;
    }

    y = textY + 6;
  }

  // ── Footer on each page ────────────────────────────────────
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    const pageHeight = doc.internal.pageSize.getHeight();

    // Footer line
    doc.setDrawColor(...AMBER);
    doc.setLineWidth(0.8);
    doc.line(margin, pageHeight - 16, pageWidth - margin, pageHeight - 16);

    // Footer text
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7);
    doc.setTextColor(...MID_GRAY);
    doc.text(
      "CATWATCH — Drone-Based Equipment Inspection Platform",
      margin,
      pageHeight - 12
    );
    doc.text(
      `Generated: ${new Date().toLocaleString()}`,
      margin,
      pageHeight - 8
    );
    doc.text(
      `Page ${i} of ${pageCount}`,
      pageWidth - margin,
      pageHeight - 12,
      { align: "right" }
    );
    doc.text(
      "Built by Syed Aabis Akhtar & Even Chen — HackIllinois 2026",
      pageWidth - margin,
      pageHeight - 8,
      { align: "right" }
    );
  }

  return doc;
}
