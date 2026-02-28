import { notFound } from "next/navigation";
import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { SEVERITY_COLORS, ZONE_LABELS, type ZoneId } from "@/lib/constants";
import Link from "next/link";
import { DownloadPDFButton } from "@/components/download-pdf-button";
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <Link
          href="/dashboard/inspections"
          style={{ fontSize: 14, color: "var(--text-muted)" }}
        >
          Inspections
        </Link>
        <span style={{ color: "var(--text-dim)" }}>/</span>
        <h1 className="mono" style={{ fontSize: 20, fontWeight: 700, color: "var(--amber)" }}>
          {inspectionSession.id.slice(0, 8)}
        </h1>
        <span
          className={
            inspectionSession.status === "active"
              ? "badge badge-green"
              : "badge badge-gray"
          }
        >
          {inspectionSession.status}
        </span>
        <div style={{ marginLeft: "auto" }}>
          <DownloadPDFButton
            inspection={{
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
            }}
          />
        </div>
      </div>

      {/* Metadata */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
        <MetaCard
          label="Date"
          value={new Date(inspectionSession.createdAt).toLocaleDateString()}
        />
        <MetaCard label="Mode" value={inspectionSession.mode} />
        <MetaCard
          label="Duration"
          value={duration !== null ? `${duration} min` : "In progress"}
        />
        <MetaCard
          label="Coverage"
          value={`${Math.round(inspectionSession.coveragePct)}%`}
        />
      </div>
      {inspectionSession.unitSerial && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
          <MetaCard label="Unit Serial" value={inspectionSession.unitSerial} />
          {inspectionSession.model && (
            <MetaCard label="Model" value={inspectionSession.model} />
          )}
          {inspectionSession.fleetTag && (
            <MetaCard label="Fleet" value={inspectionSession.fleetTag} />
          )}
        </div>
      )}

      {/* Findings */}
      <div>
        <h2 style={{ marginBottom: 16, fontSize: 18, fontWeight: 600 }}>
          Findings ({inspectionSession.findings.length})
        </h2>
        {inspectionSession.findings.length === 0 ? (
          <div
            className="card"
            style={{ padding: 24, textAlign: "center", fontSize: 14, color: "var(--text-dim)" }}
          >
            No findings recorded.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {inspectionSession.findings.map((f) => {
              const sev = f.rating as keyof typeof SEVERITY_COLORS;
              const colors = SEVERITY_COLORS[sev] || SEVERITY_COLORS.GRAY;
              const zoneLabel =
                ZONE_LABELS[f.zone as ZoneId] || f.zone;
              return (
                <div
                  key={f.id}
                  className="finding-row"
                  style={{
                    borderRadius: "var(--radius)",
                    border: `1px solid ${colors.border}`,
                    padding: 16,
                    background: colors.bg,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: colors.text }}>
                      {f.rating}
                    </span>
                    <span style={{ fontSize: 14, color: "var(--text-muted)" }}>{zoneLabel}</span>
                    <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-dim)" }}>
                      {new Date(f.createdAt).toLocaleTimeString()}
                    </span>
                  </div>
                  <p style={{ marginTop: 4, fontSize: 14, color: "var(--text-muted)" }}>{f.description}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Fleet similar findings */}
      <FleetSimilarFindings
        unitSerial={inspectionSession.unitSerial ?? null}
        findings={inspectionSession.findings.map((f) => ({
          zone: f.zone,
          rating: f.rating,
          description: f.description,
        }))}
      />

      {/* Report */}
      {inspectionSession.report && (
        <div>
          <h2 style={{ marginBottom: 16, fontSize: 18, fontWeight: 600 }}>Report</h2>
          <div className="card" style={{ padding: 24 }}>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 13, color: "var(--text-muted)", lineHeight: 1.6 }}>
              {typeof inspectionSession.report.data === "string"
                ? inspectionSession.report.data
                : JSON.stringify(inspectionSession.report.data, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

function MetaCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ fontSize: 12, color: "var(--text-dim)" }}>{label}</div>
      <div style={{ marginTop: 4, fontSize: 14, fontWeight: 500, textTransform: "capitalize" }}>{value}</div>
    </div>
  );
}
