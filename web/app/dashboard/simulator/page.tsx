"use client";

import { lazy, Suspense, useEffect, useState } from "react";

const DamageSimulator = lazy(() =>
  import("@/components/damage-simulator").then((m) => ({ default: m.DamageSimulator }))
);

function LoadingState() {
  return (
    <div style={{
      height: "calc(100vh - 160px)", display: "flex",
      alignItems: "center", justifyContent: "center",
      color: "var(--text-dim)", fontSize: 13,
    }}>
      Loading simulator…
    </div>
  );
}

export default function SimulatorPage() {
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.02em" }}>
          Damage Simulator
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 4 }}>
          Click on any zone of the CAT 797F to simulate and visualize inspection damage.
        </p>
      </div>
      {mounted ? (
        <Suspense fallback={<LoadingState />}>
          <DamageSimulator />
        </Suspense>
      ) : (
        <LoadingState />
      )}
    </div>
  );
}
