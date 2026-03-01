import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import { InspectionsTable } from "@/components/inspections-table";

export default async function InspectionsPage() {
  const session = await getSession();
  if (!session) return null;

  const sessions = await prisma.session.findMany({
    where: { userId: session.userId },
    orderBy: { createdAt: "desc" },
    include: {
      _count: { select: { findings: true } },
      findings: { select: { rating: true } },
    },
  });

  const rows = sessions.map((s) => ({
    id: s.id,
    createdAt: s.createdAt.toISOString(),
    mode: s.mode,
    status: s.status,
    endedAt: s.endedAt?.toISOString() ?? null,
    coveragePct: s.coveragePct,
    findingsCount: s._count.findings,
    redCount: s.findings.filter((f) => f.rating === "RED").length,
    yellowCount: s.findings.filter((f) => f.rating === "YELLOW").length,
  }));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Inspections</h1>
        <p style={{ marginTop: 4, fontSize: 14, color: "var(--text-muted)" }}>
          Each inspection session is created when a drone connects via the SDK.
        </p>
      </div>

      <InspectionsTable rows={rows} />
    </div>
  );
}
