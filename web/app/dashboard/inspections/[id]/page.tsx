import { notFound } from "next/navigation";
import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { SEVERITY_COLORS } from "@/lib/constants";
import Link from "next/link";
import { ReportPreview } from "@/components/report-preview";
import { FleetSimilarFindings } from "@/components/fleet-similar-findings";

export default async function InspectionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await getSession();
  if (!session) return null;

  const { id } = await params;

  const inspectionSession = await prisma.session.findFirst({
    where: { id, userId: session.userId },
    include: {
      findings: { orderBy: { createdAt: "asc" } },
      report: true,
    },
  });

  if (!inspectionSession) notFound();

  const duration = inspectionSession.endedAt
    ? Math.round(
      (new Date(inspectionSession.endedAt).getTime() -
        new Date(inspectionSession.createdAt).getTime()) /
      60000,
    )
    : null;

  const inspectionData = {
    sessionId: inspectionSession.id,
    mode: inspectionSession.mode,
    status: inspectionSession.status,
    createdAt: inspectionSession.createdAt.toISOString(),
    endedAt: inspectionSession.endedAt?.toISOString() ?? null,
    coveragePct: inspectionSession.coveragePct,
    zonesSeen: inspectionSession.zonesSeen,
    findings: inspectionSession.findings.map((f) => ({
      zone: f.zone,
      rating: f.rating,
      description: f.description,
      createdAt: f.createdAt.toISOString(),
    })),
    report: inspectionSession.report
      ? { data: inspectionSession.report.data }
      : null,
  };

  const redCount = inspectionSession.findings.filter((f) => f.rating === "RED").length;
  const yellowCount = inspectionSession.findings.filter((f) => f.rating === "YELLOW").length;
  const greenCount = inspectionSession.findings.filter((f) => f.rating === "GREEN").length;

  return (
    <div className="inspection-detail-page" style={{ display: "flex", flexDirection: "column", gap: 36 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link href="/dashboard/inspections" style={{ fontSize: 13, color: "var(--text-dim)" }}>
            Inspections
          </Link>
          <span style={{ color: "var(--text-dim)", fontSize: 13 }}>/</span>
          <h1 className="mono" style={{ fontSize: 18, fontWeight: 700, color: "var(--amber)", margin: 0 }}>
            {inspectionSession.id.slice(0, 8)}
          </h1>
          <span className={inspectionSession.status === "active" ? "badge badge-green" : "badge badge-gray"}>
            {inspectionSession.status}
          </span>
        </div>
        <div className="header-meta" style={{ display: "flex", gap: 16, fontSize: 13, color: "var(--text-muted)" }}>
          <span>{new Date(inspectionSession.createdAt).toLocaleDateString()}</span>
          <span style={{ textTransform: "capitalize" }}>{inspectionSession.mode}</span>
          <span>{duration !== null ? `${duration} min` : "Active"}</span>
          <span>{Math.round(inspectionSession.coveragePct)}% coverage</span>
          {inspectionSession.unitSerial && (
            <span className="mono" style={{ color: "var(--amber)" }}>{inspectionSession.unitSerial}</span>
          )}
        </div>
      </div>

      {/* Summary strip */}
      <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", padding: "16px 20px", background: "var(--bg-card)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <SeverityChip label="RED" count={redCount} color={SEVERITY_COLORS.RED} />
          <SeverityChip label="YEL" count={yellowCount} color={SEVERITY_COLORS.YELLOW} />
          <SeverityChip label="GRN" count={greenCount} color={SEVERITY_COLORS.GREEN} />
        </div>
        <span style={{ fontSize: 13, color: "var(--text-dim)" }}>
          {inspectionSession.findings.length} findings
        </span>
        {inspectionSession.unitSerial && (
          <div style={{ fontSize: 13 }}>
            <span className="mono" style={{ color: "var(--amber)", fontWeight: 600 }}>{inspectionSession.unitSerial}</span>
            {inspectionSession.model && <span style={{ color: "var(--text-dim)", marginLeft: 8 }}>{inspectionSession.model}</span>}
          </div>
        )}
      </div>

      {/* Report — full width */}
      <div className="report-section" style={{ padding: 32, background: "var(--bg-card)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
        <ReportPreview inspection={inspectionData} />
      </div>

      {/* Fleet findings */}
      <FleetSimilarFindings
        unitSerial={inspectionSession.unitSerial ?? null}
        findings={inspectionSession.findings.map((f) => ({
          zone: f.zone,
          rating: f.rating,
          description: f.description,
        }))}
      />
    </div>
  );
}

function SeverityChip({
  label,
  count,
  color,
}: {
  label: string;
  count: number;
  color: { bg: string; border: string; text: string };
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 6,
        background: count > 0 ? color.bg : "transparent",
        border: `1px solid ${count > 0 ? color.border : "var(--border)"}`,
      }}
    >
      <span style={{ fontSize: 16, fontWeight: 700, color: count > 0 ? color.text : "var(--text-dim)" }}>
        {count}
      </span>
      <span style={{ fontSize: 11, fontWeight: 500, color: count > 0 ? color.text : "var(--text-dim)" }}>
        {label}
      </span>
    </div>
  );
}
