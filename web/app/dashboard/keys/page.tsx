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

      {/* How it works card */}
      <div
        className="card"
        style={{ padding: 20, borderColor: "var(--border-hover)" }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            marginBottom: 12,
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--amber)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--amber)" }}>
            How API keys work
          </span>
        </div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--text-dim)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 4,
              }}
            >
              1. Create a key
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Give it a name to identify which device or project it belongs to.
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--text-dim)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 4,
              }}
            >
              2. Use in SDK
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Pass the key to{" "}
              <code
                className="mono"
                style={{
                  fontSize: 12,
                  padding: "1px 4px",
                  borderRadius: 3,
                  background: "var(--bg)",
                  border: "1px solid var(--border)",
                }}
              >
                CatWatch(api_key=&quot;...&quot;)
              </code>{" "}
              in your Python script.
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: "var(--text-dim)",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 4,
              }}
            >
              3. View results
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
              Inspection sessions and findings will appear automatically in the
              dashboard.
            </div>
          </div>
        </div>
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

      {/* SDK quick-reference */}
      <div className="card" style={{ padding: 20 }}>
        <h3
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text-muted)",
            marginBottom: 10,
          }}
        >
          SDK Quick Reference
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div>
            <span
              style={{
                fontSize: 12,
                color: "var(--text-dim)",
                fontWeight: 500,
              }}
            >
              Install
            </span>
            <pre
              className="mono"
              style={{
                marginTop: 4,
                fontSize: 12,
                color: "var(--text-muted)",
                background: "var(--bg)",
                padding: "6px 10px",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
              }}
            >
              pip install catwatch
            </pre>
          </div>
          <div>
            <span
              style={{
                fontSize: 12,
                color: "var(--text-dim)",
                fontWeight: 500,
              }}
            >
              Connect &amp; run
            </span>
            <pre
              className="mono"
              style={{
                marginTop: 4,
                fontSize: 12,
                color: "var(--text-muted)",
                background: "var(--bg)",
                padding: "6px 10px",
                borderRadius: "var(--radius)",
                border: "1px solid var(--border)",
                whiteSpace: "pre-wrap",
              }}
            >
              {`from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0)  # 0 = webcam, RTSP url, or picamera2

@cw.on_detection
def on_det(msg):
    print(f"{len(msg['detections'])} detections")

@cw.on_analysis
def on_analysis(msg):
    print(f"[{msg['data']['severity']}] {msg['data']['description']}")

cw.run()`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
