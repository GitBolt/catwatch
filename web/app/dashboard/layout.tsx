import Link from "next/link";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: "100vh" }}>
      <nav style={{ borderBottom: "1px solid var(--border)", background: "rgba(17,24,39,0.5)" }}>
        <div className="container" style={{ display: "flex", alignItems: "center", gap: 24, height: 56 }}>
          <Link href="/dashboard" style={{ fontWeight: 700, color: "var(--amber)" }}>
            CatWatch
          </Link>
          <Link href="/dashboard" style={{ fontSize: 14, color: "var(--text-muted)" }}>
            Overview
          </Link>
          <Link href="/dashboard/inspections" style={{ fontSize: 14, color: "var(--text-muted)" }}>
            Inspections
          </Link>
          <Link href="/dashboard/keys" style={{ fontSize: 14, color: "var(--text-muted)" }}>
            API Keys
          </Link>
        </div>
      </nav>
      <main className="container" style={{ paddingTop: 32, paddingBottom: 32 }}>
        {children}
      </main>
    </div>
  );
}
