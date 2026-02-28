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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>API Keys</h1>

      <form onSubmit={createKey} style={{ display: "flex", gap: 12 }}>
        <input
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder='Key name (e.g. "my drone")'
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

      {keys.length === 0 ? (
        <div
          className="card"
          style={{ padding: 32, textAlign: "center", color: "var(--text-dim)" }}
        >
          No API keys yet. Create one to get started.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {keys.map((k) => (
            <div
              key={k.id}
              className="card"
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
            >
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <div style={{ fontWeight: 500 }}>{k.name}</div>
                <div className="mono" style={{ fontSize: 14, color: "var(--text-muted)" }}>{k.key}</div>
                <div style={{ fontSize: 12, color: "var(--text-dim)" }}>
                  Created {new Date(k.createdAt).toLocaleDateString()}
                  {k.lastUsed &&
                    ` · Last used ${new Date(k.lastUsed).toLocaleDateString()}`}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => copyKey(k)}
                  className="btn btn-secondary btn-small"
                >
                  {copiedId === k.id ? "Copied!" : "Copy"}
                </button>
                <button
                  onClick={() => deleteKey(k.id)}
                  className="btn btn-danger btn-small"
                >
                  Revoke
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
