"use client";

import { Magic } from "magic-sdk";
import { useRouter } from "next/navigation";
import { useState } from "react";

let magic: InstanceType<typeof Magic> | null = null;

function getMagic() {
  if (typeof window === "undefined") return null;
  if (!magic) {
    magic = new Magic(process.env.NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY!);
  }
  return magic;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const m = getMagic()!;
      const didToken = await m.auth.loginWithEmailOTP({ email });

      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ didToken }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Login failed");
      }

      router.push("/dashboard");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Login failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "100%", maxWidth: 360, padding: 32 }}>
        <div style={{ marginBottom: 32, display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="CatWatch" width={48} height={48} style={{ borderRadius: 8, marginBottom: 12 }} />
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--amber)", letterSpacing: "-0.02em", marginBottom: 6 }}>
            CatWatch
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5 }}>
            Drone-powered equipment inspection platform.
            <br />
            Sign in to manage API keys and view inspection reports.
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email" style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--text-muted)", marginBottom: 6 }}>
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="input"
            style={{ marginBottom: 16 }}
          />
          {error && <div className="alert-error" style={{ marginBottom: 16 }}>{error}</div>}
          <button type="submit" disabled={loading} className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
            {loading ? "Verifying..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
