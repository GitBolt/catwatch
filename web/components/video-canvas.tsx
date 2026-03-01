"use client";

import { useEffect, useRef, type RefObject } from "react";

interface Props {
  frameRef: RefObject<Blob | null>;
  width?: number;
  height?: number;
}

export function VideoCanvas({ frameRef, width = 960, height = 540 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const dimsRef = useRef({ w: 0, h: 0 });
  const renderingRef = useRef(false);

  useEffect(() => {
    let running = true;

    function tick() {
      if (!running) return;

      const blob = frameRef.current;
      if (blob && !renderingRef.current) {
        frameRef.current = null;
        renderingRef.current = true;

        const canvas = canvasRef.current;
        if (!canvas) {
          renderingRef.current = false;
          requestAnimationFrame(tick);
          return;
        }

        if (!ctxRef.current) {
          ctxRef.current = canvas.getContext("2d");
        }
        const ctx = ctxRef.current;
        if (!ctx) {
          renderingRef.current = false;
          requestAnimationFrame(tick);
          return;
        }

        createImageBitmap(blob)
          .then((bitmap) => {
            if (dimsRef.current.w !== bitmap.width || dimsRef.current.h !== bitmap.height) {
              canvas.width = bitmap.width;
              canvas.height = bitmap.height;
              dimsRef.current = { w: bitmap.width, h: bitmap.height };
            }
            ctx.drawImage(bitmap, 0, 0);
            bitmap.close();
            renderingRef.current = false;
          })
          .catch(() => {
            renderingRef.current = false;
          });
      }

      requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);

    return () => {
      running = false;
    };
  }, [frameRef]);

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
