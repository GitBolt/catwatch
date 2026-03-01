import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

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

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" });
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

type RGB = [number, number, number];

function getRatingColor(rating: string): { bg: RGB; text: RGB } {
  switch (rating.toUpperCase()) {
    case "GREEN": return { bg: [...GREEN_BG] as RGB, text: [...GREEN_TEXT] as RGB };
    case "YELLOW": return { bg: [...YELLOW_BG] as RGB, text: [...YELLOW_TEXT] as RGB };
    case "RED": return { bg: [...RED_BG] as RGB, text: [...RED_TEXT] as RGB };
    default: return { bg: [...LIGHT_GRAY] as RGB, text: [...DARK_GRAY] as RGB };
  }
}

function getDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const mins = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000);
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function humanizeZone(zone: string): string {
  return zone
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const RATING_ORDER: Record<string, number> = { RED: 3, YELLOW: 2, GREEN: 1 };

async function loadLogoBase64(): Promise<string | null> {
  try {
    const res = await fetch("/logo.png");
    const blob = await res.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onloadend = () => resolve(reader.result as string);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

export async function generateInspectionPDF(data: InspectionPDFData): Promise<jsPDF> {
  const logoB64 = await loadLogoBase64();
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 14;
  const contentWidth = pageWidth - margin * 2;
  let y = 12;

  // ── Header Band ─────────────────────────────────────────
  doc.setFillColor(...AMBER);
  doc.rect(0, 0, pageWidth, 28, "F");

  if (logoB64) {
    try { doc.addImage(logoB64, "PNG", margin, 3, 22, 22); } catch { /* skip */ }
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(22);
  doc.setTextColor(...BLACK);
  doc.text("CATWATCH", margin + 25, 18);

  doc.setFontSize(14);
  doc.text("Equipment Inspection Report", pageWidth - margin, 14, { align: "right" });

  doc.setFontSize(8);
  doc.setTextColor(...DARK_GRAY);
  doc.text(`Report ID: ${data.sessionId.slice(0, 12)}`, pageWidth - margin, 22, { align: "right" });

  y = 34;

  // ── Session Info ────────────────────────────────────────
  doc.setFillColor(...BLACK);
  doc.rect(margin, y, contentWidth, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...WHITE);
  doc.text(`  INSPECTION SESSION: ${data.mode.toUpperCase()} MODE`, margin + 2, y + 5);
  y += 10;

  const redCount = data.findings.filter((f) => f.rating === "RED").length;
  const yellowCount = data.findings.filter((f) => f.rating === "YELLOW").length;
  const greenCount = data.findings.filter((f) => f.rating === "GREEN").length;

  autoTable(doc, {
    startY: y,
    head: [],
    body: [
      ["Session ID", data.sessionId],
      ["Date", formatDate(data.createdAt)],
      ["Time", formatTime(data.createdAt)],
      ["Status", data.status.charAt(0).toUpperCase() + data.status.slice(1)],
      ["Duration", getDuration(data.createdAt, data.endedAt)],
      ["Coverage", `${Math.round(data.coveragePct)}%`],
      ["Total Findings", `${data.findings.length} (${redCount} RED, ${yellowCount} YELLOW, ${greenCount} GREEN)`],
    ],
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: { fontSize: 8, cellPadding: 2, lineColor: [...TABLE_BORDER], lineWidth: 0.3 },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 40, fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY] },
      1: { textColor: [...BLACK] },
    },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── Zone Summary (data-driven) ──────────────────────────
  doc.setFillColor(...BLACK);
  doc.rect(margin, y, contentWidth, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...WHITE);
  doc.text("  ZONE SUMMARY", margin + 2, y + 5);
  y += 10;

  // Group findings by zone, compute worst rating per zone
  const zoneSummary = new Map<string, { worst: string; count: number; descriptions: string[] }>();
  data.findings.forEach((f) => {
    const key = f.zone || "general";
    const existing = zoneSummary.get(key);
    if (existing) {
      existing.count++;
      if ((RATING_ORDER[f.rating] || 0) > (RATING_ORDER[existing.worst] || 0)) {
        existing.worst = f.rating;
      }
      if (f.rating !== "GREEN" && existing.descriptions.length < 3) {
        existing.descriptions.push(f.description);
      }
    } else {
      zoneSummary.set(key, {
        worst: f.rating,
        count: 1,
        descriptions: f.rating !== "GREEN" ? [f.description] : [],
      });
    }
  });

  // Sort: RED first, then YELLOW, then GREEN
  const sortedZones = [...zoneSummary.entries()].sort(
    (a, b) => (RATING_ORDER[b[1].worst] || 0) - (RATING_ORDER[a[1].worst] || 0)
  );

  const zoneRows: any[][] = sortedZones.map(([zone, info]) => {
    const colors = getRatingColor(info.worst);
    const remarks = info.descriptions.length > 0
      ? info.descriptions.join("; ")
      : info.worst === "GREEN" ? "No issues detected" : "";
    return [
      { content: humanizeZone(zone), styles: { fontStyle: "bold" as const } },
      {
        content: info.worst,
        styles: { fillColor: [...colors.bg], textColor: [...colors.text], fontStyle: "bold" as const },
      },
      { content: `${info.count}`, styles: { halign: "center" as const } },
      { content: remarks, styles: {} },
    ];
  });

  if (zoneRows.length === 0) {
    zoneRows.push([
      { content: "No zones inspected", styles: { fontStyle: "italic" as const } },
      { content: "—", styles: {} },
      { content: "0", styles: { halign: "center" as const } },
      { content: "Insufficient data for assessment", styles: {} },
    ]);
  }

  autoTable(doc, {
    startY: y,
    head: [[
      { content: "Zone", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
      { content: "Rating", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
      { content: "Findings", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
      { content: "Remarks", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
    ]],
    body: zoneRows,
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: { fontSize: 8, cellPadding: 2.5, lineColor: [...TABLE_BORDER], lineWidth: 0.3, textColor: [...BLACK] },
    columnStyles: { 0: { cellWidth: 38 }, 1: { cellWidth: 18, halign: "center" }, 2: { cellWidth: 18, halign: "center" }, 3: {} },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── RED & YELLOW Findings Detail ────────────────────────
  const criticalFindings = data.findings.filter((f) => f.rating === "RED" || f.rating === "YELLOW");

  if (criticalFindings.length > 0) {
    if (y > 230) { doc.addPage(); y = 14; }

    doc.setFillColor(...BLACK);
    doc.rect(margin, y, contentWidth, 7, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...WHITE);
    doc.text("  ACTION ITEMS — RED & YELLOW FINDINGS", margin + 2, y + 5);
    y += 10;

    const criticalRows = criticalFindings
      .sort((a, b) => (RATING_ORDER[b.rating] || 0) - (RATING_ORDER[a.rating] || 0))
      .map((f) => {
        const colors = getRatingColor(f.rating);
        return [
          formatTime(f.createdAt),
          { content: humanizeZone(f.zone || "general"), styles: { fontStyle: "bold" as const } },
          { content: f.rating, styles: { fillColor: colors.bg, textColor: colors.text, fontStyle: "bold" as const, halign: "center" as const } },
          f.description,
        ];
      });

    autoTable(doc, {
      startY: y,
      head: [[
        { content: "Time", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Zone", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Rating", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Description", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
      ]],
      body: criticalRows,
      theme: "grid",
      margin: { left: margin, right: margin },
      styles: { fontSize: 7.5, cellPadding: 2, lineColor: [...TABLE_BORDER], lineWidth: 0.3, textColor: [...BLACK] },
      columnStyles: { 0: { cellWidth: 20 }, 1: { cellWidth: 32 }, 2: { cellWidth: 18, halign: "center" }, 3: {} },
    });

    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ── Full Findings Log ───────────────────────────────────
  if (data.findings.length > 0) {
    if (y > 230) { doc.addPage(); y = 14; }

    doc.setFillColor(...BLACK);
    doc.rect(margin, y, contentWidth, 7, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...WHITE);
    doc.text("  COMPLETE FINDINGS LOG", margin + 2, y + 5);
    y += 10;

    const allRows = data.findings.map((f) => {
      const colors = getRatingColor(f.rating);
      return [
        formatTime(f.createdAt),
        { content: humanizeZone(f.zone || "general"), styles: { fontStyle: "bold" as const } },
        { content: f.rating, styles: { fillColor: colors.bg, textColor: colors.text, fontStyle: "bold" as const, halign: "center" as const } },
        f.description,
      ];
    });

    autoTable(doc, {
      startY: y,
      head: [[
        { content: "Time", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Zone", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Rating", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
        { content: "Description", styles: { fillColor: [...LIGHT_GRAY], textColor: [...DARK_GRAY], fontStyle: "bold" } },
      ]],
      body: allRows,
      theme: "grid",
      margin: { left: margin, right: margin },
      styles: { fontSize: 7.5, cellPadding: 2, lineColor: [...TABLE_BORDER], lineWidth: 0.3, textColor: [...BLACK] },
      columnStyles: { 0: { cellWidth: 20 }, 1: { cellWidth: 32 }, 2: { cellWidth: 18, halign: "center" }, 3: {} },
    });

    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ── AI Executive Summary ────────────────────────────────
  if (data.report) {
    if (y > 220) { doc.addPage(); y = 14; }

    doc.setFillColor(...BLACK);
    doc.rect(margin, y, contentWidth, 7, "F");
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(...WHITE);
    doc.text("  AI EXECUTIVE SUMMARY", margin + 2, y + 5);
    y += 10;

    let summaryText = "";
    if (typeof data.report.data === "string") {
      summaryText = data.report.data;
    } else if (data.report.data && typeof data.report.data === "object") {
      const rd = data.report.data as Record<string, unknown>;
      if (rd.ai_executive_summary) {
        summaryText = String(rd.ai_executive_summary);
      } else {
        summaryText = JSON.stringify(data.report.data, null, 2);
      }
    }

    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(...DARK_GRAY);

    const lines = doc.splitTextToSize(summaryText, contentWidth - 8);
    const lineHeight = 3.5;
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

  // ── Footer ──────────────────────────────────────────────
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    const pageHeight = doc.internal.pageSize.getHeight();

    doc.setDrawColor(...AMBER);
    doc.setLineWidth(0.8);
    doc.line(margin, pageHeight - 16, pageWidth - margin, pageHeight - 16);

    doc.setFont("helvetica", "normal");
    doc.setFontSize(7);
    doc.setTextColor(...MID_GRAY);
    doc.text("CATWATCH — AI-Powered Equipment Inspection", margin, pageHeight - 12);
    doc.text(`Generated: ${new Date().toLocaleString()}`, margin, pageHeight - 8);
    doc.text(`Page ${i} of ${pageCount}`, pageWidth - margin, pageHeight - 12, { align: "right" });
  }

  return doc;
}
