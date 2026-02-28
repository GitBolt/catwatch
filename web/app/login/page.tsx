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
      <div style={{ width: "100%", maxWidth: 380, padding: 32 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--amber)", marginBottom: 4 }}>
          CatWatch
        </h1>
        <p style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 24 }}>
          Equipment inspection platform
        </p>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email" style={{ display: "block", fontSize: 14, fontWeight: 500, color: "var(--text-muted)", marginBottom: 6 }}>
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
            {loading ? "Verifying..." : "Sign in with email"}
          </button>
        </form>
      </div>
    </div>
  );
}
