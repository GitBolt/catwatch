"use client";

import dynamic from "next/dynamic";
import type { FindingEntry } from "./model-viewer";

const ModelViewer = dynamic(
  () => import("./model-viewer").then((m) => m.ModelViewer),
  {
    ssr: false,
    loading: () => (
      <div
        style={{
          height: 480,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text-dim)",
          fontSize: 13,
          background: "#1a1918",
          borderRadius: "var(--radius)",
        }}
      >
        Loading 3D model…
      </div>
    ),
  },
);

export function ModelViewerLoader({ findings }: { findings: FindingEntry[] }) {
  return <ModelViewer findings={findings} />;
}
