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

const AMBER: RGB = [245, 197, 24];
const BLACK: RGB = [0, 0, 0];
const WHITE: RGB = [255, 255, 255];
const DARK_GRAY: RGB = [60, 60, 60];
const MID_GRAY: RGB = [128, 128, 128];
const LIGHT_GRAY: RGB = [240, 240, 240];
const TABLE_BORDER: RGB = [180, 180, 180];

const GOOD_BG: RGB = [220, 245, 220];
const FAIR_BG: RGB = [255, 248, 210];
const POOR_BG: RGB = [255, 220, 220];
const GOOD_TEXT: RGB = [34, 120, 34];
const FAIR_TEXT: RGB = [150, 120, 0];
const POOR_TEXT: RGB = [180, 40, 40];

type RGB = [number, number, number];

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" });
}

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

function ratingToCode(rating: string): string {
  switch (rating.toUpperCase()) {
    case "GREEN": return "Good";
    case "YELLOW": return "Fair";
    case "RED": return "Poor";
    default: return rating;
  }
}

function getCodeStyle(code: string): { bg: RGB; text: RGB } {
  switch (code) {
    case "Good": return { bg: GOOD_BG, text: GOOD_TEXT };
    case "Fair": return { bg: FAIR_BG, text: FAIR_TEXT };
    case "Poor": return { bg: POOR_BG, text: POOR_TEXT };
    default: return { bg: LIGHT_GRAY, text: DARK_GRAY };
  }
}

function getDuration(start: string, end: string | null): string {
  if (!end) return "In progress";
  const mins = Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000);
  if (mins < 60) return `${mins} min`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function humanize(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const CODE_ORDER: Record<string, number> = { Poor: 3, Fair: 2, Good: 1 };

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

function sectionBand(doc: jsPDF, y: number, title: string, margin: number, width: number): number {
  doc.setFillColor(...AMBER);
  doc.rect(margin, y, width, 7, "F");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.setTextColor(...BLACK);
  doc.text(title.toUpperCase(), margin + 3, y + 5);
  return y + 10;
}

function checkPage(doc: jsPDF, y: number, needed: number): number {
  if (y + needed > doc.internal.pageSize.getHeight() - 20) {
    doc.addPage();
    return 14;
  }
  return y;
}

export async function generateInspectionPDF(data: InspectionPDFData): Promise<jsPDF> {
  const logoB64 = await loadLogoBase64();
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 14;
  const contentWidth = pageWidth - margin * 2;

  const redCount = data.findings.filter((f) => f.rating === "RED").length;
  const yellowCount = data.findings.filter((f) => f.rating === "YELLOW").length;
  const greenCount = data.findings.filter((f) => f.rating === "GREEN").length;

  const overallCode = redCount > 0 ? "Poor" : yellowCount > 0 ? "Fair" : "Good";
  const reportData = data.report?.data as Record<string, unknown> | undefined;

  // ── Header Band ─────────────────────────────────────────
  doc.setFillColor(...AMBER);
  doc.rect(0, 0, pageWidth, 26, "F");

  if (logoB64) {
    try { doc.addImage(logoB64, "PNG", margin, 2, 22, 22); } catch { /* skip */ }
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.setTextColor(...BLACK);
  doc.text("CATWATCH", margin + 25, 16);

  doc.setFontSize(14);
  doc.setFont("helvetica", "bold");
  doc.text("Equipment Inspection Report", pageWidth - margin, 12, { align: "right" });

  doc.setFontSize(8);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...DARK_GRAY);
  doc.text(`Report ID: ${data.sessionId.slice(0, 12)}`, pageWidth - margin, 20, { align: "right" });

  let y = 32;

  // ── INSPECTION DETAILS ──────────────────────────────────
  y = sectionBand(doc, y, "Inspection Details", margin, contentWidth);

  const equipType = reportData?.unit
    ? (reportData.unit as Record<string, unknown>).model || "AI-Identified"
    : data.mode === "cat" ? "CAT Equipment" : "General";

  autoTable(doc, {
    startY: y,
    head: [],
    body: [
      ["Inspector", "AI-Assisted (CatWatch)"],
      ["Inspection Date", formatDate(data.createdAt)],
      ["Report Date", formatDate(new Date().toISOString())],
      ["Location", (reportData as any)?.location || "—"],
      ["Duration", getDuration(data.createdAt, data.endedAt)],
      ["Mode", data.mode.toUpperCase()],
    ],
    theme: "grid",
    margin: { left: margin, right: pageWidth / 2 + 2 },
    styles: { fontSize: 8, cellPadding: 2, lineColor: TABLE_BORDER, lineWidth: 0.3 },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 35, fillColor: LIGHT_GRAY, textColor: DARK_GRAY },
      1: { textColor: BLACK },
    },
  });

  const detailsLeftY = (doc as any).lastAutoTable.finalY;

  autoTable(doc, {
    startY: y,
    head: [],
    body: [
      ["Equipment", String(equipType)],
      ["Serial / ID", String(reportData?.unit ? (reportData.unit as Record<string, unknown>).serial || "—" : "—")],
      ["Operating Hours", String(reportData?.unit ? (reportData.unit as Record<string, unknown>).operating_hours || "—" : "—")],
      ["Coverage", `${Math.round(data.coveragePct)}%`],
      ["Total Findings", `${data.findings.length}`],
      ["Status", data.status.charAt(0).toUpperCase() + data.status.slice(1)],
    ],
    theme: "grid",
    margin: { left: pageWidth / 2 + 2, right: margin },
    styles: { fontSize: 8, cellPadding: 2, lineColor: TABLE_BORDER, lineWidth: 0.3 },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 35, fillColor: LIGHT_GRAY, textColor: DARK_GRAY },
      1: { textColor: BLACK },
    },
  });

  y = Math.max(detailsLeftY, (doc as any).lastAutoTable.finalY) + 4;

  // ── OVERALL ASSESSMENT ──────────────────────────────────
  y = sectionBand(doc, y, "Overall Assessment", margin, contentWidth);

  const codeStyle = getCodeStyle(overallCode);
  autoTable(doc, {
    startY: y,
    head: [],
    body: [
      [
        { content: "Overall Code", styles: { fontStyle: "bold" as const, fillColor: LIGHT_GRAY, textColor: DARK_GRAY } },
        { content: overallCode.toUpperCase(), styles: { fontStyle: "bold" as const, fillColor: codeStyle.bg, textColor: codeStyle.text, halign: "center" as const, fontSize: 10 } },
        { content: `${redCount} Poor  ·  ${yellowCount} Fair  ·  ${greenCount} Good`, styles: { textColor: MID_GRAY } },
      ],
    ],
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: { fontSize: 8, cellPadding: 3, lineColor: TABLE_BORDER, lineWidth: 0.3, textColor: BLACK },
    columnStyles: { 0: { cellWidth: 35 }, 1: { cellWidth: 25 }, 2: {} },
  });

  y = (doc as any).lastAutoTable.finalY + 4;

  // ── AI EXECUTIVE SUMMARY ────────────────────────────────
  const summary = reportData?.ai_executive_summary as string | undefined;
  if (summary) {
    y = checkPage(doc, y, 25);
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(...MID_GRAY);
    const lines = doc.splitTextToSize(summary, contentWidth - 8);
    doc.setDrawColor(...TABLE_BORDER);
    doc.setLineWidth(0.3);
    const boxH = lines.length * 3.5 + 6;
    doc.rect(margin, y, contentWidth, boxH);
    let ty = y + 4;
    for (const line of lines) {
      doc.text(line, margin + 4, ty);
      ty += 3.5;
    }
    y = ty + 4;
  }

  // ── INSPECTION FINDINGS (CAT-style: Component | Code | Remarks) ──
  y = checkPage(doc, y, 20);
  y = sectionBand(doc, y, "Inspection Findings", margin, contentWidth);

  const findingRows = data.findings
    .map((f) => {
      const code = ratingToCode(f.rating);
      const style = getCodeStyle(code);
      return {
        code,
        codeOrder: CODE_ORDER[code] || 0,
        row: [
          { content: humanize(f.zone || "General"), styles: { fontStyle: "bold" as const } },
          { content: code, styles: { fillColor: style.bg, textColor: style.text, fontStyle: "bold" as const, halign: "center" as const } },
          { content: f.description, styles: {} },
        ],
        time: formatTime(f.createdAt),
      };
    })
    .sort((a, b) => b.codeOrder - a.codeOrder);

  if (findingRows.length === 0) {
    findingRows.push({
      code: "—",
      codeOrder: 0,
      row: [
        { content: "No findings recorded", styles: {} },
        { content: "—", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" as const, halign: "center" as const } },
        { content: "Insufficient inspection data", styles: {} },
      ],
      time: "",
    });
  }

  autoTable(doc, {
    startY: y,
    head: [[
      { content: "Component", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
      { content: "CODE", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
      { content: "REMARKS", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
    ]],
    body: findingRows.map((r) => r.row),
    theme: "grid",
    margin: { left: margin, right: margin },
    styles: { fontSize: 7.5, cellPadding: 2.5, lineColor: TABLE_BORDER, lineWidth: 0.3, textColor: BLACK },
    columnStyles: { 0: { cellWidth: 40 }, 1: { cellWidth: 18, halign: "center" }, 2: {} },
  });

  y = (doc as any).lastAutoTable.finalY + 6;

  // ── ACTION ITEMS (Fair & Poor only) ─────────────────────
  const actionFindings = data.findings.filter((f) => f.rating === "RED" || f.rating === "YELLOW");

  if (actionFindings.length > 0) {
    y = checkPage(doc, y, 20);
    y = sectionBand(doc, y, "Action Items", margin, contentWidth);

    const actionRows = actionFindings
      .sort((a, b) => (CODE_ORDER[ratingToCode(b.rating)] || 0) - (CODE_ORDER[ratingToCode(a.rating)] || 0))
      .map((f) => {
        const code = ratingToCode(f.rating);
        const style = getCodeStyle(code);
        const priority = f.rating === "RED" ? "Immediate" : "Scheduled";
        return [
          { content: priority, styles: { fontStyle: "bold" as const, textColor: style.text } },
          { content: humanize(f.zone || "General"), styles: { fontStyle: "bold" as const } },
          { content: code, styles: { fillColor: style.bg, textColor: style.text, fontStyle: "bold" as const, halign: "center" as const } },
          { content: f.description, styles: {} },
        ];
      });

    autoTable(doc, {
      startY: y,
      head: [[
        { content: "Priority", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "Component", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "CODE", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "Description / Action Required", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
      ]],
      body: actionRows,
      theme: "grid",
      margin: { left: margin, right: margin },
      styles: { fontSize: 7.5, cellPadding: 2.5, lineColor: TABLE_BORDER, lineWidth: 0.3, textColor: BLACK },
      columnStyles: { 0: { cellWidth: 22 }, 1: { cellWidth: 35 }, 2: { cellWidth: 16, halign: "center" }, 3: {} },
    });

    y = (doc as any).lastAutoTable.finalY + 6;
  }

  // ── COMPLETE FINDINGS LOG ───────────────────────────────
  if (data.findings.length > 0) {
    y = checkPage(doc, y, 20);
    y = sectionBand(doc, y, "Complete Findings Log", margin, contentWidth);

    const allRows = data.findings.map((f) => {
      const code = ratingToCode(f.rating);
      const style = getCodeStyle(code);
      return [
        formatTime(f.createdAt),
        { content: humanize(f.zone || "General"), styles: { fontStyle: "bold" as const } },
        { content: code, styles: { fillColor: style.bg, textColor: style.text, fontStyle: "bold" as const, halign: "center" as const } },
        f.description,
      ];
    });

    autoTable(doc, {
      startY: y,
      head: [[
        { content: "Time", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "Component", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "CODE", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
        { content: "Remarks", styles: { fillColor: LIGHT_GRAY, textColor: DARK_GRAY, fontStyle: "bold" } },
      ]],
      body: allRows,
      theme: "grid",
      margin: { left: margin, right: margin },
      styles: { fontSize: 7.5, cellPadding: 2, lineColor: TABLE_BORDER, lineWidth: 0.3, textColor: BLACK },
      columnStyles: { 0: { cellWidth: 20 }, 1: { cellWidth: 35 }, 2: { cellWidth: 16, halign: "center" }, 3: {} },
    });

    y = (doc as any).lastAutoTable.finalY + 6;
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
