"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

interface InspectionRow {
  id: string;
  createdAt: string;
  mode: string;
  status: string;
  endedAt: string | null;
  coveragePct: number;
  findingsCount: number;
  redCount: number;
  yellowCount: number;
}

interface Props {
  rows: InspectionRow[];
}

export function InspectionsTable({ rows }: Props) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (rows.length === 0) {
    return (
      <div
        className="card"
        style={{ padding: 32, textAlign: "center", color: "var(--text-dim)" }}
      >
        No inspections yet. Inspections appear here automatically when a
        drone connects using the SDK with your API key.
      </div>
    );
  }

  const allSelected = selected.size === rows.length && rows.length > 0;

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
    } else {
      setSelected(new Set(rows.map((r) => r.id)));
    }
  }

  function toggleOne(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleDelete() {
    if (selected.size === 0) return;
    setDeleting(true);
    try {
      const res = await fetch("/api/inspections", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [...selected] }),
      });
      if (res.ok) {
        setSelected(new Set());
        setConfirmDelete(false);
        router.refresh();
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Action bar — visible when items selected */}
      {selected.size > 0 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "8px 16px",
            borderRadius: "var(--radius)",
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
          }}
        >
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {selected.size} selected
          </span>
          {confirmDelete ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
                Delete {selected.size} inspection{selected.size !== 1 ? "s" : ""}?
              </span>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="btn btn-danger btn-small"
              >
                {deleting ? "Deleting..." : "Yes, delete"}
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="btn btn-secondary btn-small"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              className="btn btn-danger btn-small"
            >
              Delete selected
            </button>
          )}
        </div>
      )}

      <div className="card table-responsive" style={{ padding: 0, overflow: "hidden" }}>
        <table style={{ width: "100%", fontSize: 14, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left", fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              <th style={{ padding: "10px 12px", fontWeight: 500, width: 36 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  style={{ cursor: "pointer", accentColor: "var(--amber)" }}
                />
              </th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Session</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Date</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Mode</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Duration</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Coverage</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Findings</th>
              <th style={{ padding: "10px 16px", fontWeight: 500 }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const duration = s.endedAt
                ? Math.round(
                  (new Date(s.endedAt).getTime() -
                    new Date(s.createdAt).getTime()) /
                  60000,
                )
                : null;

              const isSelected = selected.has(s.id);

              return (
                <tr
                  key={s.id}
                  style={{
                    borderBottom: "1px solid var(--border)",
                    background: isSelected ? "rgba(196, 162, 76, 0.04)" : undefined,
                  }}
                >
                  <td style={{ padding: "12px 12px" }}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleOne(s.id)}
                      style={{ cursor: "pointer", accentColor: "var(--amber)" }}
                    />
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <Link
                      href={
                        s.status === "active"
                          ? `/session/${s.id}`
                          : `/dashboard/inspections/${s.id}`
                      }
                      className="mono"
                      style={{ color: "var(--amber)" }}
                    >
                      {s.id.slice(0, 8)}
                    </Link>
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                    {new Date(s.createdAt).toLocaleDateString()}{" "}
                    {new Date(s.createdAt).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </td>
                  <td style={{ padding: "12px 16px", textTransform: "capitalize", color: "var(--text-muted)" }}>
                    {s.mode}
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                    {duration !== null ? `${duration}m` : "-"}
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-muted)" }}>
                    {Math.round(s.coveragePct)}%
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", gap: 8, fontSize: 12 }}>
                      {s.redCount > 0 && (
                        <span style={{ color: "var(--red)" }}>
                          {s.redCount} red
                        </span>
                      )}
                      {s.yellowCount > 0 && (
                        <span style={{ color: "var(--yellow)" }}>
                          {s.yellowCount} yellow
                        </span>
                      )}
                      {s.redCount === 0 && s.yellowCount === 0 && (
                        <span style={{ color: "var(--text-dim)" }}>
                          {s.findingsCount} total
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span
                      className={
                        s.status === "active"
                          ? "badge badge-green"
                          : "badge badge-gray"
                      }
                    >
                      {s.status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
