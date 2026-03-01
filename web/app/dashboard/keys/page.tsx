"use client";

import { useEffect, useState } from "react";

interface ApiKeyRow {
  id: string;
  name: string;
  key: string;
  createdAt: string;
  lastUsed: string | null;
}

export default function KeysPage() {
  const [keys, setKeys] = useState<ApiKeyRow[]>([]);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    fetchKeys();
  }, []);

  async function fetchKeys() {
    const res = await fetch("/api/keys");
    if (res.ok) setKeys(await res.json());
  }

  async function createKey(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    const res = await fetch("/api/keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      setName("");
      await fetchKeys();
    }
    setCreating(false);
  }

  async function deleteKey(id: string) {
    await fetch(`/api/keys/${id}`, { method: "DELETE" });
    await fetchKeys();
  }

  function copyKey(key: ApiKeyRow) {
    navigator.clipboard.writeText(key.key);
    setCopiedId(key.id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function copySnippet(apiKey: string) {
    const snippet = `from catwatch import CatWatch

cw = CatWatch(api_key="${apiKey}")
cw.connect(source=0)  # webcam, RTSP url, or picamera2
cw.run()`;
    navigator.clipboard.writeText(snippet);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>API Keys</h1>
        <p style={{ marginTop: 4, fontSize: 14, color: "var(--text-muted)" }}>
          API keys authenticate your drone&apos;s SDK connection to the CatWatch
          inspection backend. Each key can create inspection sessions that appear
          here in the dashboard.
        </p>
      </div>

      {/* SDK docs link */}
      <div
        className="card"
        style={{ padding: 16, display: "flex", alignItems: "center", justifyContent: "space-between", borderColor: "var(--border-hover)" }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
          </svg>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Create a key below, then pass it to{" "}
            <code className="mono" style={{ fontSize: 12, padding: "1px 4px", borderRadius: 3, background: "var(--bg)", border: "1px solid var(--border)" }}>
              CatWatch(api_key=&quot;...&quot;)
            </code>{" "}
            in the SDK.
          </span>
        </div>
        <a
          href="https://github.com/GitBolt/catwatch/blob/main/sdk/README.md"
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-secondary btn-small"
          style={{ flexShrink: 0 }}
        >
          SDK Docs
        </a>
      </div>

      {/* Create key form */}
      <div>
        <h2
          style={{
            fontSize: 14,
            fontWeight: 600,
            marginBottom: 10,
            color: "var(--text-muted)",
          }}
        >
          Create new key
        </h2>
        <form onSubmit={createKey} style={{ display: "flex", gap: 12 }}>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='Key name (e.g. "Raspberry Pi drone", "jobsite-alpha")'
            className="input"
            style={{ flex: 1 }}
          />
          <button
            type="submit"
            disabled={creating}
            className="btn btn-primary"
          >
            {creating ? "Creating..." : "Create Key"}
          </button>
        </form>
      </div>

      {/* Key list */}
      <div>
        <h2
          style={{
            fontSize: 14,
            fontWeight: 600,
            marginBottom: 10,
            color: "var(--text-muted)",
          }}
        >
          Your keys {keys.length > 0 && `(${keys.length})`}
        </h2>

        {keys.length === 0 ? (
          <div
            className="card"
            style={{
              padding: 32,
              textAlign: "center",
              color: "var(--text-dim)",
            }}
          >
            No API keys yet. Create one above to connect the CatWatch SDK.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {keys.map((k) => (
              <div
                key={k.id}
                className="card key-row"
                style={{ padding: 16 }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                    }}
                  >
                    <span style={{ fontWeight: 600, fontSize: 15 }}>
                      {k.name}
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: "var(--text-dim)",
                      }}
                    >
                      Created{" "}
                      {new Date(k.createdAt).toLocaleDateString()}
                      {k.lastUsed &&
                        ` · Last used ${new Date(k.lastUsed).toLocaleDateString()}`}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      onClick={() => copyKey(k)}
                      className="btn btn-secondary btn-small"
                    >
                      {copiedId === k.id ? "Copied!" : "Copy Key"}
                    </button>
                    <button
                      onClick={() => copySnippet(k.key)}
                      className="btn btn-secondary btn-small"
                      title="Copy a ready-to-run Python snippet with this key"
                    >
                      Copy Snippet
                    </button>
                    <button
                      onClick={() => deleteKey(k.id)}
                      className="btn btn-danger btn-small"
                    >
                      Revoke
                    </button>
                  </div>
                </div>
                <div
                  className="mono"
                  style={{
                    fontSize: 13,
                    color: "var(--text-muted)",
                    background: "var(--bg)",
                    padding: "6px 10px",
                    borderRadius: "var(--radius)",
                    border: "1px solid var(--border)",
                  }}
                >
                  {k.key}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
}
