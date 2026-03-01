"use client";

import { useCallback, useRef, useState } from "react";

interface DamageItem {
  zone: string;
  severity: string;
  description: string;
  estimatedRepairCost: string;
  safetyImpact: string;
}

interface ClaimData {
  claimTitle: string;
  claimDate: string;
  policySection: string;
  incidentSummary: string;
  equipmentDetails: {
    make: string;
    model: string;
    type: string;
    serial: string;
    estimatedValue: string;
  };
  damageAssessment: DamageItem[];
  totalEstimatedCost: string;
  urgencyLevel: string;
  recommendedActions: string[];
  supportingEvidence: string;
  declaration: string;
}

interface InspectionInput {
  sessionId: string;
  createdAt: string;
  endedAt: string | null;
  unitSerial: string | null;
  unitModel: string | null;
  fleetTag: string | null;
  location: string | null;
  coveragePct: number;
  findings: { zone: string; rating: string; description: string; createdAt: string }[];
}

const SEV_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  Critical: { bg: "rgba(184,92,92,0.10)", text: "#d08080", border: "#b85c5c" },
  Warning: { bg: "rgba(176,147,64,0.10)", text: "#cdb460", border: "#b09340" },
  Minor: { bg: "rgba(106,158,114,0.10)", text: "#82b88a", border: "#6a9e72" },
};

const URGENCY_COLORS: Record<string, string> = {
  Immediate: "#c45050",
  Urgent: "#c9a832",
  Standard: "#5a9e62",
};

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h3 style={{
      fontSize: 14, fontWeight: 700, color: "var(--amber)",
      borderBottom: "1px solid var(--border)", paddingBottom: 8,
      marginBottom: 16, marginTop: 28, letterSpacing: "-0.01em",
    }}>
      {children}
    </h3>
  );
}

function ClaimDocument({ claim, inspection }: { claim: ClaimData; inspection: InspectionInput }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
      {/* Header */}
      <div style={{ textAlign: "center", marginBottom: 24 }}>
        <div style={{ fontSize: 11, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
          Heavy Equipment Insurance Claim
        </div>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: "8px 0 4px", letterSpacing: "-0.02em" }}>
          {claim.claimTitle}
        </h2>
        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
          Claim Date: {claim.claimDate} &middot; Inspection #{inspection.sessionId.slice(0, 8)}
        </div>
      </div>

      {/* Urgency + Policy */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <div style={{
          flex: 1, padding: "12px 16px", borderRadius: "var(--radius)",
          border: `1px solid ${URGENCY_COLORS[claim.urgencyLevel] ?? "var(--border)"}`,
          background: `${URGENCY_COLORS[claim.urgencyLevel] ?? "var(--border)"}10`,
        }}>
          <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>Urgency</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: URGENCY_COLORS[claim.urgencyLevel] ?? "var(--text)" }}>
            {claim.urgencyLevel}
          </div>
        </div>
        <div style={{
          flex: 1, padding: "12px 16px", borderRadius: "var(--radius)",
          border: "1px solid var(--border)", background: "var(--bg)",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>Policy Section</div>
          <div style={{ fontSize: 13, fontWeight: 600 }}>{claim.policySection}</div>
        </div>
        <div style={{
          flex: 1, padding: "12px 16px", borderRadius: "var(--radius)",
          border: "1px solid var(--border)", background: "var(--bg)",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-dim)", textTransform: "uppercase", marginBottom: 4 }}>Est. Total Cost</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#c45050" }}>{claim.totalEstimatedCost}</div>
        </div>
      </div>

      {/* Equipment Details */}
      <SectionHeader>Equipment Details</SectionHeader>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px 20px", fontSize: 13 }}>
        {[
          ["Make", claim.equipmentDetails.make],
          ["Model", claim.equipmentDetails.model],
          ["Type", claim.equipmentDetails.type],
          ["Serial", claim.equipmentDetails.serial],
          ["Est. Value", claim.equipmentDetails.estimatedValue],
          ["Fleet Tag", inspection.fleetTag ?? "N/A"],
        ].map(([label, value]) => (
          <div key={label}>
            <span style={{ color: "var(--text-dim)", fontSize: 11 }}>{label}</span>
            <div style={{ fontWeight: 600, marginTop: 2 }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Incident Summary */}
      <SectionHeader>Incident Summary</SectionHeader>
      <p style={{ fontSize: 13, lineHeight: 1.7, color: "var(--text-muted)", whiteSpace: "pre-line" }}>
        {claim.incidentSummary}
      </p>

      {/* Damage Assessment */}
      <SectionHeader>Damage Assessment ({claim.damageAssessment.length} items)</SectionHeader>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {claim.damageAssessment.map((d, i) => {
          const colors = SEV_COLORS[d.severity] ?? SEV_COLORS.Minor;
          return (
            <div key={i} style={{
              padding: "14px 16px", borderRadius: "var(--radius)",
              border: `1px solid ${colors.border}40`,
              background: colors.bg,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: "2px 8px",
                    borderRadius: 4, background: `${colors.border}25`, color: colors.text,
                    textTransform: "uppercase",
                  }}>
                    {d.severity}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{d.zone}</span>
                </div>
                <span style={{ fontSize: 12, fontWeight: 600, color: colors.text }}>{d.estimatedRepairCost}</span>
              </div>
              <p style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5, margin: 0 }}>
                {d.description}
              </p>
              {d.safetyImpact && (
                <p style={{ fontSize: 11, color: "var(--text-dim)", marginTop: 6, margin: "6px 0 0" }}>
                  <strong style={{ color: "#c45050" }}>Safety:</strong> {d.safetyImpact}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Recommended Actions */}
      <SectionHeader>Recommended Actions</SectionHeader>
      <ol style={{ margin: 0, padding: "0 0 0 20px", fontSize: 13, lineHeight: 1.7, color: "var(--text-muted)" }}>
        {claim.recommendedActions.map((a, i) => (
          <li key={i} style={{ marginBottom: 4 }}>{a}</li>
        ))}
      </ol>

      {/* Supporting Evidence */}
      <SectionHeader>Supporting Evidence</SectionHeader>
      <p style={{ fontSize: 13, lineHeight: 1.7, color: "var(--text-muted)" }}>
        {claim.supportingEvidence}
      </p>

      {/* Declaration */}
      <SectionHeader>Declaration</SectionHeader>
      <div style={{
        padding: "16px 20px", borderRadius: "var(--radius)",
        border: "1px solid var(--border)", background: "var(--bg)",
        fontSize: 12, lineHeight: 1.7, color: "var(--text-muted)",
      }}>
        {claim.declaration}
        <div style={{ marginTop: 24, display: "flex", gap: 40 }}>
          <div>
            <div style={{ borderBottom: "1px solid var(--text-dim)", width: 200, marginBottom: 4 }}>&nbsp;</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Claimant Signature</div>
          </div>
          <div>
            <div style={{ borderBottom: "1px solid var(--text-dim)", width: 140, marginBottom: 4 }}>&nbsp;</div>
            <div style={{ fontSize: 11, color: "var(--text-dim)" }}>Date</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function InsuranceClaimButton({ inspection }: { inspection: InspectionInput }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [claim, setClaim] = useState<ClaimData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  const generateClaim = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/generate-claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(inspection),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Failed to generate claim");
      setClaim(data.claim);
      setOpen(true);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [inspection]);

  const handlePrint = useCallback(() => {
    if (!printRef.current) return;
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;
    printWindow.document.write(`<!DOCTYPE html><html><head><title>Insurance Claim - ${inspection.sessionId.slice(0, 8)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1a1a1a; padding: 40px; font-size: 13px; line-height: 1.6; }
  h2 { font-size: 20px; margin: 8px 0; }
  h3 { font-size: 14px; font-weight: 700; border-bottom: 1px solid #ddd; padding-bottom: 6px; margin: 24px 0 12px; }
  p { margin-bottom: 8px; }
  ol { padding-left: 20px; }
  li { margin-bottom: 4px; }
  .sev-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-transform: uppercase; }
  .damage-card { padding: 12px 16px; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 8px; }
  .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px 20px; }
  .meta-row { display: flex; gap: 12px; margin-bottom: 16px; }
  .meta-box { flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 6px; }
  .meta-label { font-size: 10px; text-transform: uppercase; color: #888; margin-bottom: 2px; }
  .sig-line { border-bottom: 1px solid #333; width: 200px; margin-top: 24px; margin-bottom: 4px; }
  @media print { body { padding: 20px; } }
</style></head><body>`);
    printWindow.document.write(printRef.current.innerHTML
      .replace(/style="[^"]*"/g, "")
    );
    printWindow.document.write("</body></html>");
    printWindow.document.close();
    printWindow.print();
  }, [inspection.sessionId]);

  const hasFindings = inspection.findings.length > 0;

  if (!hasFindings) return null;

  return (
    <>
      <button
        onClick={generateClaim}
        disabled={loading}
        style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "9px 18px", fontSize: 13, fontWeight: 600,
          background: loading ? "var(--bg-elevated)" : "var(--bg-card)",
          border: "1px solid var(--border)", borderRadius: "var(--radius)",
          color: loading ? "var(--text-dim)" : "var(--text)",
          cursor: loading ? "wait" : "pointer",
          transition: "background 0.15s",
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
        {loading ? "Generating Claim…" : "File Insurance Claim"}
      </button>

      {error && (
        <span style={{ fontSize: 12, color: "#c45050", marginLeft: 12 }}>{error}</span>
      )}

      {/* Modal */}
      {open && claim && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 1000,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.6)", backdropFilter: "blur(6px)",
          }}
          onClick={() => setOpen(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "90vw", maxWidth: 820,
              maxHeight: "90vh", overflow: "hidden",
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 12, display: "flex", flexDirection: "column",
            }}
          >
            {/* Toolbar */}
            <div style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "14px 20px", borderBottom: "1px solid var(--border)", flexShrink: 0,
            }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>Insurance Claim Document</span>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handlePrint}
                  style={{
                    display: "flex", alignItems: "center", gap: 6,
                    padding: "6px 14px", fontSize: 12, fontWeight: 600,
                    background: "var(--amber)", border: "none", borderRadius: 6,
                    cursor: "pointer", color: "#141313",
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="6 9 6 2 18 2 18 9" />
                    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
                    <rect x="6" y="14" width="12" height="8" />
                  </svg>
                  Print / Save PDF
                </button>
                <button
                  onClick={() => setOpen(false)}
                  style={{
                    padding: "6px 12px", fontSize: 14, background: "none",
                    border: "1px solid var(--border)", borderRadius: 6,
                    cursor: "pointer", color: "var(--text-dim)",
                  }}
                >
                  &times;
                </button>
              </div>
            </div>

            {/* Content */}
            <div ref={printRef} style={{ flex: 1, overflowY: "auto", padding: "24px 32px 40px" }}>
              <ClaimDocument claim={claim} inspection={inspection} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
