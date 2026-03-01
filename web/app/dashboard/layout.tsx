import Link from "next/link";
import Image from "next/image";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <nav style={{ borderBottom: "1px solid var(--border)", background: "rgba(20,19,19,0.85)", backdropFilter: "blur(16px)" }}>
        <div className="container nav-inner" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, height: 56 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <Link href="/dashboard" style={{ display: "flex", alignItems: "center" }}>
              <Image
                src="/logo.png"
                alt="CatWatch"
                width={36}
                height={36}
                style={{ borderRadius: 6 }}
              />
            </Link>
            <Link href="/dashboard" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Overview
            </Link>
            <Link href="/dashboard/inspections" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Inspections
            </Link>
            <Link href="/dashboard/simulator" className="nav-link" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Simulator
            </Link>
          </div>
          <Link
            href="/dashboard/settings"
            className="nav-link"
            style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 8, borderRadius: "var(--radius)", color: "var(--text-muted)" }}
            title="Settings"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </Link>
        </div>
      </nav>
      <main className="container" style={{ paddingTop: 32, paddingBottom: 48, flex: 1 }}>
        {children}
      </main>
      <footer className="site-footer">
        <div className="container">
          <div className="footer-inner">
            <div className="footer-brand">
              <Image
                src="/logo.png"
                alt="CatWatch"
                width={24}
                height={24}
                style={{ borderRadius: 4 }}
              />
            </div>
            <div className="footer-credit">
              Built by{" "}
              <a href="https://aabis.dev" target="_blank" rel="noopener noreferrer" className="footer-name">Aabis</a> and{" "}
              <a href="https://github.com/feeniks01" target="_blank" rel="noopener noreferrer" className="footer-name">Evan</a> for{" "}
              <span className="footer-event">HackIllinois 2026</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
