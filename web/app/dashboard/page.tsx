import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import Link from "next/link";
import { FindingsChart } from "@/components/findings-chart";

export default async function DashboardPage() {
  const session = await getSession();
  if (!session) return null;

  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const [totalSessions, totalFindings, apiKeyCount, recentSessions, sessionsForChart] =
    await Promise.all([
      prisma.session.count({ where: { userId: session.userId } }),
      prisma.finding.count({
        where: { session: { userId: session.userId } },
      }),
      prisma.apiKey.count({ where: { userId: session.userId } }),
      prisma.session.findMany({
        where: { userId: session.userId },
        orderBy: { createdAt: "desc" },
        take: 5,
        include: { _count: { select: { findings: true } } },
      }),
      prisma.session.findMany({
        where: {
          userId: session.userId,
          createdAt: { gte: thirtyDaysAgo },
        },
        include: { _count: { select: { findings: true } } },
      }),
    ]);

  const findingsByDay = new Map<string, number>();
  for (const s of sessionsForChart) {
    const day = s.createdAt.toISOString().slice(0, 10);
    findingsByDay.set(day, (findingsByDay.get(day) || 0) + s._count.findings);
  }

  const chartData: { date: string; label: string; findings: number }[] = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().slice(0, 10);
    const label = d.toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "2-digit" });
    chartData.push({
      date: dateStr,
      label,
      findings: findingsByDay.get(dateStr) || 0,
    });
  }

  const lastInspectionDate = recentSessions[0]
    ? new Date(recentSessions[0].createdAt).toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "2-digit" })
    : "—";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.02em" }}>
          Dashboard
        </h1>
        <p style={{ marginTop: 4, fontSize: 14, color: "var(--text-muted)" }}>
          Overview of your drone inspections and platform activity.
        </p>
      </div>

      <div
        className="stats-grid-4"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 16,
        }}
      >
        <StatCard label="Total Inspections" value={totalSessions} />
        <StatCard label="Total Findings" value={totalFindings} />
        <StatCard label="Last Inspection" value={lastInspectionDate} />
      </div>

      {/* Quick-start guide if no sessions yet */}
      {totalSessions === 0 && apiKeyCount === 0 && (
        <div
          className="card"
          style={{
            padding: 24,
            borderColor: "var(--border-hover)",
          }}
        >
          <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
            Getting Started
          </h2>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Step
              number={1}
              title="Create an API Key"
              description="Go to Settings and create a key to authenticate your drone's SDK connection."
              link="/dashboard/settings"
              linkText="Create API Key →"
            />
            <Step
              number={2}
              title="Install the Python SDK"
              description="pip install catwatch"
              code
            />
            <Step
              number={3}
              title="Connect your camera feed"
              description='from catwatch import CatWatch
cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0)
cw.run()'
              code
            />
          </div>
        </div>
      )}

      <div className="dashboard-two-col" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, alignItems: "start" }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>
            Findings per Day
          </h2>
          <FindingsChart data={chartData} />
        </div>

        <div>
          <div
            style={{
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <h2 style={{ fontSize: 18, fontWeight: 600 }}>
              Recent Inspections
            </h2>
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
            style={{
              padding: 32,
              textAlign: "center",
              color: "var(--text-dim)",
            }}
          >
            No inspections yet. Create an API key, install the SDK, and connect
            your drone to start inspecting.
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
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <span
                    className={
                      s.status === "active"
                        ? "dot dot-green"
                        : "dot dot-gray"
                    }
                  />
                  <span
                    className="mono"
                    style={{
                      fontSize: 14,
                      color: "var(--text-muted)",
                    }}
                  >
                    {s.id.slice(0, 8)}
                  </span>
                  <span
                    style={{
                      fontSize: 14,
                      textTransform: "capitalize",
                      color: "var(--text-muted)",
                    }}
                  >
                    {s.mode}
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 16,
                    fontSize: 14,
                    color: "var(--text-dim)",
                  }}
                >
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
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card stat-card">
      <div
        style={{
          fontSize: 28,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          fontVariantNumeric: typeof value === "number" ? "tabular-nums" : undefined,
        }}
      >
        {value}
      </div>
      <div style={{ marginTop: 4, fontSize: 13, color: "var(--text-muted)" }}>
        {label}
      </div>
    </div>
  );
}

function Step({
  number,
  title,
  description,
  link,
  linkText,
  code,
}: {
  number: number;
  title: string;
  description: string;
  link?: string;
  linkText?: string;
  code?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        alignItems: "flex-start",
      }}
    >
      <div
        style={{
          width: 24,
          height: 24,
          borderRadius: "50%",
          background: "var(--amber-dim)",
          color: "var(--amber)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 12,
          fontWeight: 700,
          flexShrink: 0,
          marginTop: 2,
        }}
      >
        {number}
      </div>
      <div>
        <div style={{ fontWeight: 600, fontSize: 14 }}>{title}</div>
        {code ? (
          <pre
            className="mono"
            style={{
              marginTop: 4,
              fontSize: 12,
              color: "var(--text-muted)",
              background: "var(--bg)",
              padding: "8px 12px",
              borderRadius: "var(--radius)",
              border: "1px solid var(--border)",
              whiteSpace: "pre-wrap",
            }}
          >
            {description}
          </pre>
        ) : (
          <p
            style={{
              marginTop: 2,
              fontSize: 13,
              color: "var(--text-muted)",
            }}
          >
            {description}
          </p>
        )}
        {link && (
          <Link
            href={link}
            style={{
              display: "inline-block",
              marginTop: 6,
              fontSize: 13,
              color: "var(--amber)",
            }}
          >
            {linkText}
          </Link>
        )}
      </div>
    </div>
  );
}
