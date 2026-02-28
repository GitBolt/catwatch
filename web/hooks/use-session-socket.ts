"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Detection,
  AnalysisData,
  FindingData,
  ServerMessage,
} from "@/lib/types";

interface SessionState {
  connected: boolean;
  frame: string | null;
  frameId: number;
  detections: Detection[];
  analysis: AnalysisData | null;
  findings: FindingData[];
  zonesSeen: Set<string>;
  coverage: number;
  mode: string;
  yoloMs: number;
  voiceAnswer: string | null;
  report: Record<string, unknown> | null;
  send: (msg: Record<string, unknown>) => void;
}

const BACKEND_WS = process.env.NEXT_PUBLIC_BACKEND_WS || "wss://gitbolt--dronecat-web.modal.run";

export function useSessionSocket(sessionId: string | null): SessionState {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [frame, setFrame] = useState<string | null>(null);
  const [frameId, setFrameId] = useState(0);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [findings, setFindings] = useState<FindingData[]>([]);
  const [zonesSeen, setZonesSeen] = useState<Set<string>>(new Set());
  const [coverage, setCoverage] = useState(0);
  const [mode, setMode] = useState("general");
  const [yoloMs, setYoloMs] = useState(0);
  const [voiceAnswer, setVoiceAnswer] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    let reconnectTimer: ReturnType<typeof setTimeout>;
    let backoff = 2000;

    function connect() {
      const url = `${BACKEND_WS}/ws/view/${sessionId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        backoff = 2000;
      };

      ws.onclose = () => {
        setConnected(false);
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 1.5, 30000);
      };

      ws.onerror = () => ws.close();

      ws.onmessage = (event) => {
        const msg: ServerMessage = JSON.parse(event.data);

        switch (msg.type) {
          case "frame":
            setFrame(msg.data);
            setFrameId(msg.frame_id);
            break;

          case "detection":
            setDetections(msg.detections);
            setCoverage(msg.coverage);
            setMode(msg.mode);
            setYoloMs(msg.yolo_ms);
            break;

          case "analysis":
            setAnalysis(msg.data);
            break;

          case "finding":
            setFindings((prev) => [...prev, msg.data]);
            break;

          case "voice_answer":
            setVoiceAnswer(msg.text);
            // Auto-speak
            if ("speechSynthesis" in window) {
              const utterance = new SpeechSynthesisUtterance(msg.text);
              speechSynthesis.speak(utterance);
            }
            break;

          case "zone_first_seen":
            setZonesSeen((prev) => new Set([...prev, msg.zone]));
            break;

          case "report":
            setReport(msg.data as Record<string, unknown>);
            break;
        }
      };
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [sessionId]);

  return {
    connected,
    frame,
    frameId,
    detections,
    analysis,
    findings,
    zonesSeen,
    coverage,
    mode,
    yoloMs,
    voiceAnswer,
    report,
    send,
  };
}
