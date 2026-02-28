"use client";

import { useEffect, useRef } from "react";

interface Props {
  frame: string | null;
  width?: number;
  height?: number;
}

export function VideoCanvas({ frame, width = 960, height = 540 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!frame || !canvasRef.current) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    img.src = `data:image/jpeg;base64,${frame}`;
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
        background: "#111827",
        objectFit: "contain",
      }}
    />
  );
}
