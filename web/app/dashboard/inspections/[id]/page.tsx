import { notFound } from "next/navigation";
import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import Link from "next/link";
import { ReportPreview } from "@/components/report-preview";
import { FleetSimilarFindings } from "@/components/fleet-similar-findings";
import { ModelViewerLoader } from "@/components/model-viewer-loader";
import { InsuranceClaimButton } from "@/components/insurance-claim";

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
    unitSerial: inspectionSession.unitSerial ?? null,
    unitModel: inspectionSession.model ?? null,
    fleetTag: inspectionSession.fleetTag ?? null,
    location: (inspectionSession as Record<string, unknown>).location as string ?? null,
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
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
        <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
          <div className="header-meta" style={{ display: "flex", gap: 16, fontSize: 13, color: "var(--text-muted)" }}>
            <span>{new Date(inspectionSession.createdAt).toLocaleDateString()}</span>
            <span style={{ textTransform: "capitalize" }}>{inspectionSession.mode}</span>
            <span>{duration !== null ? `${duration} min` : "Active"}</span>
            <span>{Math.round(inspectionSession.coveragePct)}% coverage</span>
            {inspectionSession.unitSerial && (
              <span className="mono" style={{ color: "var(--amber)" }}>{inspectionSession.unitSerial}</span>
            )}
          </div>
          {inspectionSession.status !== "active" && (
            <InsuranceClaimButton inspection={inspectionData} />
          )}
        </div>
      </div>

      {/* Summary strip — unit info only (findings moved to report toolbar) */}
      {(inspectionSession.unitSerial || inspectionSession.model) && (
        <div style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", padding: "16px 20px", background: "var(--bg-card)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
          {inspectionSession.unitSerial && (
            <div style={{ fontSize: 13 }}>
              <span className="mono" style={{ color: "var(--amber)", fontWeight: 600 }}>{inspectionSession.unitSerial}</span>
              {inspectionSession.model && <span style={{ color: "var(--text-dim)", marginLeft: 8 }}>{inspectionSession.model}</span>}
            </div>
          )}
        </div>
      )}

      {/* 3D Inspection View */}
      {inspectionSession.status !== "active" && inspectionData.findings.length > 0 && (
        <div style={{ padding: 24, background: "var(--bg-card)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, letterSpacing: "-0.01em" }}>
            3D Inspection View
          </h2>
          <ModelViewerLoader findings={inspectionData.findings} />
        </div>
      )}

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
