import Link from "next/link";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: "100vh" }}>
      <nav style={{ borderBottom: "1px solid var(--border)", background: "rgba(15,15,18,0.8)", backdropFilter: "blur(12px)" }}>
        <div className="container" style={{ display: "flex", alignItems: "center", gap: 24, height: 56 }}>
          <Link href="/dashboard" style={{ fontWeight: 700, fontSize: 15, color: "var(--amber)", letterSpacing: "-0.02em" }}>
            CatWatch
          </Link>
          <Link href="/dashboard" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Overview
          </Link>
          <Link href="/dashboard/inspections" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Inspections
          </Link>
          <Link href="/dashboard/keys" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
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
