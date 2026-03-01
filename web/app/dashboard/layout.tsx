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
        <div className="container nav-inner" style={{ display: "flex", alignItems: "center", gap: 24, height: 56 }}>
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
