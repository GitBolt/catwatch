"use client";

import { useEffect, useRef } from "react";

interface Props {
  frame: Blob | null;
  width?: number;
  height?: number;
}

export function VideoCanvas({ frame, width = 960, height = 540 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const renderingRef = useRef(false);
  const latestFrameRef = useRef<Blob | null>(null);

  useEffect(() => {
    if (!frame || !canvasRef.current) return;

    latestFrameRef.current = frame;

    // Skip if already decoding a frame — the next render will pick up latestFrameRef
    if (renderingRef.current) return;
    renderingRef.current = true;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      renderingRef.current = false;
      return;
    }

    function renderLatest() {
      const blob = latestFrameRef.current;
      if (!blob) {
        renderingRef.current = false;
        return;
      }
      latestFrameRef.current = null;

      createImageBitmap(blob)
        .then((bitmap) => {
          if (canvas.width !== bitmap.width) canvas.width = bitmap.width;
          if (canvas.height !== bitmap.height) canvas.height = bitmap.height;
          ctx!.drawImage(bitmap, 0, 0);
          bitmap.close();

          // If a newer frame arrived while we were decoding, render it
          if (latestFrameRef.current) {
            requestAnimationFrame(renderLatest);
          } else {
            renderingRef.current = false;
          }
        })
        .catch(() => {
          renderingRef.current = false;
        });
    }

    requestAnimationFrame(renderLatest);
  }, [frame]);

  return (
    <canvas
      ref={canvasRef}
      width={width}
      height={height}
      style={{
        height: "100%",
        width: "100%",
        borderRadius: "var(--radius)",
        background: "var(--bg-card)",
        objectFit: "contain",
      }}
    />
  );
}
