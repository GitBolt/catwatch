import { getSession } from "@/lib/auth";
import { prisma } from "@/lib/db";
import Link from "next/link";

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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Inspections</h1>
        <p style={{ marginTop: 4, fontSize: 14, color: "var(--text-muted)" }}>
          Each inspection session is created when a drone connects via the SDK.
          Click a session to view detailed findings and download the PDF report.
        </p>
      </div>

      {sessions.length === 0 ? (
        <div
          className="card"
          style={{ padding: 32, textAlign: "center", color: "var(--text-dim)" }}
        >
          No inspections yet. Inspections appear here automatically when a
          drone connects using the SDK with your API key.
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left", fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Session</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Date</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Mode</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Duration</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Coverage</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Findings</th>
                <th style={{ padding: "10px 16px", fontWeight: 500 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => {
                const duration = s.endedAt
                  ? Math.round(
                    (new Date(s.endedAt).getTime() -
                      new Date(s.createdAt).getTime()) /
                    60000,
                  )
                  : null;

                const redCount = s.findings.filter(
                  (f) => f.rating === "RED",
                ).length;
                const yellowCount = s.findings.filter(
                  (f) => f.rating === "YELLOW",
                ).length;

                return (
                  <tr
                    key={s.id}
                    style={{ borderBottom: "1px solid var(--border)" }}
                  >
                    <td style={{ padding: "12px 16px" }}>
                      <Link
                        href={
                          s.status === "active"
                            ? `/session/${s.id}`
                            : `/dashboard/inspections/${s.id}`
                        }
                        className="mono"
                        style={{ color: "var(--amber)" }}
                      >
                        {s.id.slice(0, 8)}
                      </Link>
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                      {new Date(s.createdAt).toLocaleDateString()}{" "}
                      {new Date(s.createdAt).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td style={{ padding: "12px 16px", textTransform: "capitalize", color: "var(--text-muted)" }}>
                      {s.mode}
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                      {duration !== null ? `${duration}m` : "-"}
                    </td>
                    <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                      {Math.round(s.coveragePct)}%
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                        {redCount > 0 && (
                          <span style={{ color: "var(--red)" }}>
                            {redCount} red
                          </span>
                        )}
                        {yellowCount > 0 && (
                          <span style={{ color: "var(--yellow)" }}>
                            {yellowCount} yellow
                          </span>
                        )}
                        {redCount === 0 && yellowCount === 0 && (
                          <span style={{ color: "var(--text-dim)" }}>
                            {s._count.findings} total
                          </span>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span
                        className={
                          s.status === "active"
                            ? "badge badge-green"
                            : "badge badge-gray"
                        }
                      >
                        {s.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
