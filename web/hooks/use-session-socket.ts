"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  Detection,
  AnalysisData,
  FindingData,
  EquipmentInfo,
  InsightData,
  ZoneTrend,
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

export interface SessionEndSummary {
  session_id: string;
  zones_inspected: number;
  total_zones: number;
  coverage_pct: number;
  findings_count: number;
  mode: string;
}

interface SessionState {
  connected: boolean;
  frameRef: React.RefObject<Blob | null>;
  hasFrame: boolean;
  detections: Detection[];
  analysis: AnalysisData | null;
  findings: FindingData[];
  insights: InsightData[];
  zoneTrends: Record<string, ZoneTrend>;
  zonesSeen: Set<string>;
  coverage: number;
  totalZones: number;
  mode: string;
  yoloMs: number;
  voiceAnswer: string | null;
  transcript: string | null;
  equipmentInfo: EquipmentInfo | null;
  report: Record<string, unknown> | null;
  unitSerial: string | null;
  unitModel: string | null;
  fleetTag: string | null;
  location: string | null;
  memoryKey: string | null;
  unitProfile: UnitProfile | null;
  unitProfileLoading: boolean;
  sessionEnded: SessionEndSummary | null;
  send: (msg: Record<string, unknown>) => void;
  sendAudio: (audioBase64: string) => void;
  endSession: () => void;
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
  const frameRef = useRef<Blob | null>(null);
  const hasFrameRef = useRef(false);
  const [hasFrame, setHasFrame] = useState(false);
  const [detections, setDetections] = useState<Detection[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [findings, setFindings] = useState<FindingData[]>([]);
  const [insights, setInsights] = useState<InsightData[]>([]);
  const [zoneTrends, setZoneTrends] = useState<Record<string, ZoneTrend>>({});
  const [zonesSeen, setZonesSeen] = useState<Set<string>>(new Set());
  const [coverage, setCoverage] = useState(0);
  const [totalZones, setTotalZones] = useState(0);
  const [mode, setMode] = useState("general");
  const [equipmentInfo, setEquipmentInfo] = useState<EquipmentInfo | null>(null);
  const [yoloMs, setYoloMs] = useState(0);
  const [voiceAnswer, setVoiceAnswer] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [unitSerial, setUnitSerial] = useState<string | null>(null);
  const [unitModel, setUnitModel] = useState<string | null>(null);
  const [fleetTag, setFleetTag] = useState<string | null>(null);
  const [location, setLocation] = useState<string | null>(null);
  const [geoKey, setGeoKey] = useState<string | null>(null);
  const [unitProfile, setUnitProfile] = useState<UnitProfile | null>(null);
  const [unitProfileLoading, setUnitProfileLoading] = useState(false);
  const [sessionEnded, setSessionEnded] = useState<SessionEndSummary | null>(null);

  const profileFetchedRef = useRef<string | null>(null);
  const geoAttemptedRef = useRef(false);
  const memoryKeyRef = useRef<string | null>(null);

  const memoryKey = unitSerial || location || geoKey;
  memoryKeyRef.current = memoryKey;

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const sendAudio = useCallback((audioBase64: string) => {
    send({ type: "audio_question", audio: audioBase64 });
  }, [send]);

  const endSession = useCallback(() => {
    send({ type: "end_session" });
  }, [send]);

  useEffect(() => {
    if (!memoryKey || profileFetchedRef.current === memoryKey) return;
    profileFetchedRef.current = memoryKey;

    setUnitProfileLoading(true);
    fetchUnitProfile(memoryKey).then((profile) => {
      setUnitProfile(profile);
      setUnitProfileLoading(false);

      if (profile) {
        const parts: string[] = [];
        if (profile.profile.static.length > 0) {
          parts.push("Site history: " + profile.profile.static.join(" "));
        }
        if (profile.profile.dynamic.length > 0) {
          parts.push("Recent: " + profile.profile.dynamic.join(" "));
        }
        const contextStr = parts.join("\n") || "No prior history available.";
        send({ type: "unit_context", context: contextStr });
      }
    });
  }, [memoryKey, send]);

  useEffect(() => {
    if (unitSerial || location || geoAttemptedRef.current) return;
    geoAttemptedRef.current = true;
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(3);
        const lng = pos.coords.longitude.toFixed(3);
        setGeoKey(`geo:${lat},${lng}`);
      },
      () => {},
      { timeout: 5000, maximumAge: 300000 },
    );
  }, [unitSerial, location]);

  useEffect(() => {
    if (!sessionId) return;

    let reconnectTimer: ReturnType<typeof setTimeout>;
    let backoff = 2000;
    let stopped = false;

    function connect() {
      if (stopped) return;

      const url = `${BACKEND_WS}/ws/view/${sessionId}`;
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onclose = () => {
        setConnected(false);
        if (!stopped) {
          reconnectTimer = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 1.5, 30000);
        }
      };

      ws.onerror = () => ws.close();

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          if (event.data.byteLength < 5) return;
          const jpegBytes = event.data.slice(4);
          frameRef.current = new Blob([jpegBytes], { type: "image/jpeg" });
          if (!hasFrameRef.current) {
            hasFrameRef.current = true;
            setHasFrame(true);
          }
          return;
        }

        const msg: ServerMessage = JSON.parse(event.data);

        switch (msg.type) {
          case "error":
            stopped = true;
            setConnected(false);
            ws.close();
            break;

          case "detection":
            setDetections(msg.detections);
            setCoverage(msg.coverage);
            if (msg.total_zones) setTotalZones(msg.total_zones);
            setMode(msg.mode);
            setYoloMs(msg.yolo_ms);
            break;

          case "analysis":
            setAnalysis(msg.data);
            if (memoryKeyRef.current && msg.data.findings) {
              for (const f of msg.data.findings) {
                if (typeof f === "string" && f.trim()) {
                  storeMemory(
                    memoryKeyRef.current,
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

          case "transcript":
            setTranscript(msg.text);
            break;

          case "equipment_identified":
            setEquipmentInfo(msg.data);
            if (msg.data.inspectable_zones?.length) {
              setTotalZones(msg.data.inspectable_zones.length);
            }
            break;

          case "insight":
            setInsights((prev) => [...prev.slice(-19), msg.data]);
            break;

          case "zone_trend":
            setZoneTrends((prev) => ({ ...prev, [msg.zone]: msg.trend }));
            break;

          case "zone_first_seen":
            setZonesSeen((prev) => new Set([...prev, msg.zone]));
            break;

          case "report":
            setReport(msg.data as Record<string, unknown>);
            if (memoryKeyRef.current) {
              storeReport(memoryKeyRef.current, msg.data);
            }
            break;

          case "session_state":
            backoff = 2000;
            setMode(msg.mode);
            if (msg.unit_serial) setUnitSerial(msg.unit_serial);
            if (msg.unit_model) setUnitModel(msg.unit_model);
            if (msg.fleet_tag) setFleetTag(msg.fleet_tag);
            if (msg.location) setLocation(msg.location);
            break;

          case "session_ended":
            stopped = true;
            setSessionEnded(msg.data);
            setConnected(false);
            break;
        }
      };
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [sessionId]);

  return {
    connected,
    frameRef,
    hasFrame,
    detections,
    analysis,
    findings,
    insights,
    zoneTrends,
    zonesSeen,
    coverage,
    totalZones,
    mode,
    yoloMs,
    voiceAnswer,
    transcript,
    equipmentInfo,
    report,
    unitSerial,
    unitModel,
    fleetTag,
    location,
    memoryKey,
    unitProfile,
    unitProfileLoading,
    sessionEnded,
    send,
    sendAudio,
    endSession,
  };
}
