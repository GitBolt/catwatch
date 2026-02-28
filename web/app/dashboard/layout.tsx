import Link from "next/link";
import Image from "next/image";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <nav style={{ borderBottom: "1px solid var(--border)", background: "rgba(15,15,18,0.8)", backdropFilter: "blur(12px)" }}>
        <div className="container" style={{ display: "flex", alignItems: "center", gap: 24, height: 56 }}>
          <Link href="/dashboard" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Image
              src="/logo.png"
              alt="CatWatch"
              width={36}
              height={36}
              style={{ borderRadius: 6 }}
            />
            <span style={{ fontWeight: 700, fontSize: 15, color: "var(--amber)", letterSpacing: "-0.02em" }}>
              CatWatch
            </span>
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
              <span className="footer-logo-text">CatWatch</span>
            </div>
            <div className="footer-credit">
              Built by <span className="footer-name">Syed Aabis Akhtar</span> and{" "}
              <span className="footer-name">Even Chen</span> for{" "}
              <span className="footer-event">HackIllinois 2026</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
