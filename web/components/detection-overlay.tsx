"use client";

import { useEffect, useRef } from "react";
import type { Detection } from "@/lib/types";

interface Props {
  detections: Detection[];
  width: number;
  height: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  GREEN: "#6a9e72",
  YELLOW: "#b09340",
  RED: "#b85c5c",
};

export function DetectionOverlay({ detections, width, height }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = width;
    canvas.height = height;
    ctx.clearRect(0, 0, width, height);

    for (const det of detections) {
      const [x1, y1, x2, y2] = det.bbox;
      const px = x1 * width;
      const py = y1 * height;
      const pw = (x2 - x1) * width;
      const ph = (y2 - y1) * height;

      // Color based on anomaly score
      let color = SEVERITY_COLORS.GREEN;
      if (det.anomaly_score && det.anomaly_score > 0.15) {
        color = SEVERITY_COLORS.RED;
      } else if (det.anomaly_score && det.anomaly_score > 0.05) {
        color = SEVERITY_COLORS.YELLOW;
      }

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(px, py, pw, ph);

      // Label
      const label = `${det.label} ${(det.confidence * 100).toFixed(0)}%`;
      ctx.font = "12px monospace";
      const textW = ctx.measureText(label).width;
      ctx.fillStyle = color;
      ctx.fillRect(px, py - 16, textW + 8, 16);
      ctx.fillStyle = "#000";
      ctx.fillText(label, px + 4, py - 4);
    }
  }, [detections, width, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{
        pointerEvents: "none",
        position: "absolute",
        inset: 0,
        height: "100%",
        width: "100%",
      }}
    />
  );
}
