import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import Link from "next/link";

export default async function DashboardPage() {
  const session = await getSession();
  if (!session) return null;

  const [totalSessions, totalFindings, recentSessions] = await Promise.all([
    prisma.session.count({ where: { userId: session.userId } }),
    prisma.finding.count({
      where: { session: { userId: session.userId } },
    }),
    prisma.session.findMany({
      where: { userId: session.userId },
      orderBy: { createdAt: "desc" },
      take: 5,
      include: { _count: { select: { findings: true } } },
    }),
  ]);

  const redFindings = await prisma.finding.count({
    where: { session: { userId: session.userId }, rating: "RED" },
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>Dashboard</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <StatCard label="Total Inspections" value={totalSessions} />
        <StatCard label="Total Findings" value={totalFindings} />
        <StatCard label="Red Flags" value={redFindings} />
      </div>

      <div>
        <div style={{ marginBottom: 16, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <h2 style={{ fontSize: 18, fontWeight: 600 }}>Recent Inspections</h2>
          <Link
            href="/dashboard/inspections"
            style={{ fontSize: 14, color: "var(--amber)" }}
          >
            View all
          </Link>
        </div>

        {recentSessions.length === 0 ? (
          <div
            className="card"
            style={{ padding: 32, textAlign: "center", color: "var(--text-dim)" }}
          >
            No inspections yet. Create an API key and connect your drone to get
            started.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {recentSessions.map((s) => (
              <Link
                key={s.id}
                href={
                  s.status === "active"
                    ? `/session/${s.id}`
                    : `/dashboard/inspections/${s.id}`
                }
                className="card card-hover"
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", transition: "border-color 0.15s" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span
                    className={s.status === "active" ? "dot dot-green" : "dot dot-gray"}
                  />
                  <span className="mono" style={{ fontSize: 14, color: "var(--text-muted)" }}>
                    {s.id.slice(0, 8)}
                  </span>
                  <span style={{ fontSize: 14, textTransform: "capitalize", color: "var(--text-muted)" }}>
                    {s.mode}
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 14, color: "var(--text-dim)" }}>
                  <span>{s._count.findings} findings</span>
                  <span>{Math.round(s.coveragePct)}% coverage</span>
                  <span>
                    {new Date(s.createdAt).toLocaleDateString()}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="card">
      <div style={{ fontSize: 24, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 14, color: "var(--text-muted)" }}>{label}</div>
    </div>
  );
}
