"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Detection,
  AnalysisData,
  FindingData,
  ServerMessage,
} from "@/lib/types";

export interface UnitProfile {
  profile: {
    static: string[];
    dynamic: string[];
  };
  searchResults?: {
    results: { id: string; memory?: string; chunk?: string; similarity: number }[];
    total: number;
  };
}

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
  unitSerial: string | null;
  unitModel: string | null;
  fleetTag: string | null;
  unitProfile: UnitProfile | null;
  unitProfileLoading: boolean;
  send: (msg: Record<string, unknown>) => void;
}

const BACKEND_WS = process.env.NEXT_PUBLIC_BACKEND_WS || "wss://heyaabis--dronecat-web.modal.run";

/** Store a finding in Supermemory via our API route. Fire-and-forget. */
function storeMemory(unitSerial: string, finding: string, zone: string, severity: string) {
  fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "store",
      unitSerial,
      content: `[${severity}] Zone: ${zone} — ${finding}`,
      metadata: { zone, severity, type: "finding", timestamp: new Date().toISOString() },
    }),
  }).catch((e) => console.warn("[memory] store error:", e));
}

function storeReport(unitSerial: string, reportJson: unknown) {
  fetch("/api/memory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "store_report",
      unitSerial,
      reportJson,
    }),
  }).catch((e) => console.warn("[memory] store report error:", e));
}

async function fetchUnitProfile(unitSerial: string): Promise<UnitProfile | null> {
  try {
    const res = await fetch(`/api/memory?action=profile&unitSerial=${encodeURIComponent(unitSerial)}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    console.warn("[memory] profile fetch error:", e);
    return null;
  }
}

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
  const [unitSerial, setUnitSerial] = useState<string | null>(null);
  const [unitModel, setUnitModel] = useState<string | null>(null);
  const [fleetTag, setFleetTag] = useState<string | null>(null);
  const [unitProfile, setUnitProfile] = useState<UnitProfile | null>(null);
  const [unitProfileLoading, setUnitProfileLoading] = useState(false);

  // Track unit serial to avoid duplicate profile fetches
  const profileFetchedRef = useRef<string | null>(null);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  // When we get a unit serial, fetch its Supermemory profile and send context to backend
  useEffect(() => {
    if (!unitSerial || profileFetchedRef.current === unitSerial) return;
    profileFetchedRef.current = unitSerial;

    setUnitProfileLoading(true);
    fetchUnitProfile(unitSerial).then((profile) => {
      setUnitProfile(profile);
      setUnitProfileLoading(false);

      // Compile profile into a context string and send to backend
      if (profile) {
        const parts: string[] = [];
        if (profile.profile.static.length > 0) {
          parts.push("Unit history: " + profile.profile.static.join(" "));
        }
        if (profile.profile.dynamic.length > 0) {
          parts.push("Recent: " + profile.profile.dynamic.join(" "));
        }
        const contextStr = parts.join("\n") || "No prior history available.";
        send({ type: "unit_context", context: contextStr });
      }
    });
  }, [unitSerial, send]);

  useEffect(() => {
    if (!sessionId) return;

    let reconnectTimer: ReturnType<typeof setTimeout>;
    let backoff = 2000;
    // Track unit serial within connection for memory storage
    let currentUnitSerial: string | null = null;

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
            // Store findings in Supermemory if unit is identified
            if (currentUnitSerial && msg.data.findings) {
              for (const f of msg.data.findings) {
                if (typeof f === "string" && f.trim()) {
                  storeMemory(
                    currentUnitSerial,
                    f,
                    msg.data.zone ?? "unknown",
                    msg.data.severity,
                  );
                }
              }
            }
            break;

          case "finding":
            setFindings((prev) => [...prev, msg.data]);
            break;

          case "voice_answer":
            setVoiceAnswer(msg.text);
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
            // Store report in Supermemory
            if (currentUnitSerial) {
              storeReport(currentUnitSerial, msg.data);
            }
            break;

          case "session_state":
            setMode(msg.mode);
            if (msg.unit_serial) {
              currentUnitSerial = msg.unit_serial;
              setUnitSerial(msg.unit_serial);
            }
            if (msg.unit_model) setUnitModel(msg.unit_model);
            if (msg.fleet_tag) setFleetTag(msg.fleet_tag);
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
    unitSerial,
    unitModel,
    fleetTag,
    unitProfile,
    unitProfileLoading,
    send,
  };
}
