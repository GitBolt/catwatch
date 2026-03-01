"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { useSessionSocket } from "@/hooks/use-session-socket";
import { VideoCanvas } from "@/components/video-canvas";
import { DetectionOverlay } from "@/components/detection-overlay";
import { AnalysisPanel } from "@/components/analysis-panel";
import { ZonePanel } from "@/components/zone-panel";
import { FindingsList } from "@/components/findings-list";
import { VoiceButton } from "@/components/voice-button";
import { TopBar } from "@/components/top-bar";
import { UnitHistoryPanel } from "@/components/unit-history-panel";

export default function LiveSessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 960, height: 540 });
  const [confirmEnd, setConfirmEnd] = useState(false);

  const {
    connected,
    frame,
    detections,
    analysis,
    findings,
    zonesSeen,
    coverage,
    totalZones,
    mode,
    yoloMs,
    voiceAnswer,
    transcript,
    equipmentInfo,
    unitSerial,
    unitModel,
    fleetTag,
    unitProfile,
    unitProfileLoading,
    sessionEnded,
    send,
    sendAudio,
    endSession,
  } = useSessionSocket(id);

  const handleQuestion = useCallback(
    (text: string) => {
      send({ type: "voice_question", text });
    },
    [send],
  );

  const handleModeChange = useCallback(
    (newMode: string) => {
      send({ type: "set_mode", mode: newMode });
    },
    [send],
  );

  if (sessionEnded) {
    const s = sessionEnded;
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
        <div style={{ maxWidth: 480, width: "100%", padding: 32 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 24, letterSpacing: "-0.02em" }}>
            Inspection Complete
          </h1>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 24 }}>
            <div className="card stat-card">
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.zones_inspected}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>of {s.total_zones} zones</div>
            </div>
            <div className="card stat-card">
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.coverage_pct}%</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>coverage</div>
            </div>
            <div className="card stat-card">
              <div style={{ fontSize: 28, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.findings_count}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>findings</div>
            </div>
            <div className="card stat-card">
              <div style={{ fontSize: 14, fontWeight: 600, textTransform: "uppercase", color: "var(--amber)" }}>{s.mode}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>mode</div>
            </div>
          </div>

          <div className="mono" style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 24 }}>
            Session {s.session_id}
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={() => router.push(`/dashboard/inspections/${s.session_id}`)}
              className="btn btn-primary"
            >
              View Full Report
            </button>
            <button
              onClick={() => router.push("/dashboard")}
              className="btn btn-secondary"
            >
              Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        flexDirection: "column",
        gap: 8,
        background: "var(--bg)",
        padding: 12,
      }}
    >
      <TopBar
        sessionId={id}
        connected={connected}
        mode={mode}
        yoloMs={yoloMs}
        coverage={coverage}
        totalZones={totalZones || 15}
        onModeChange={handleModeChange}
      />

      <div style={{ display: "flex", minHeight: 0, flex: 1, gap: 12 }}>
        {/* Video + Overlay */}
        <div
          ref={containerRef}
          style={{
            position: "relative",
            flex: 1,
            overflow: "hidden",
            borderRadius: "var(--radius)",
            background: "var(--bg-card)",
          }}
        >
          <VideoCanvas
            frame={frame}
            width={canvasSize.width}
            height={canvasSize.height}
          />
          <DetectionOverlay
            detections={detections}
            width={canvasSize.width}
            height={canvasSize.height}
          />
          {!connected && !frame && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-dim)",
              }}
            >
              Waiting for drone feed...
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div
          style={{
            display: "flex",
            width: 288,
            flexDirection: "column",
            gap: 12,
            overflowY: "auto",
          }}
        >
          <UnitHistoryPanel
            unitSerial={unitSerial}
            unitModel={unitModel}
            fleetTag={fleetTag}
            profile={unitProfile}
            loading={unitProfileLoading}
          />
          <AnalysisPanel analysis={analysis} />
          <ZonePanel zonesSeen={zonesSeen} coverage={coverage} totalZones={totalZones || 15} equipmentInfo={equipmentInfo} />
          <FindingsList findings={findings} />
        </div>
      </div>

      {/* Bottom bar */}
      <div
        className="card"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "8px 16px",
          background: "rgba(15, 15, 18, 0.8)",
          backdropFilter: "blur(12px)",
        }}
      >
        <VoiceButton onQuestion={handleQuestion} onAudio={sendAudio} voiceAnswer={voiceAnswer} transcript={transcript} />

        <div style={{ marginLeft: "auto" }}>
          {confirmEnd ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>End inspection?</span>
              <button onClick={() => { endSession(); setConfirmEnd(false); }} className="btn btn-danger btn-small">
                Confirm
              </button>
              <button onClick={() => setConfirmEnd(false)} className="btn btn-secondary btn-small">
                Cancel
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirmEnd(true)} className="btn btn-danger btn-small">
              End Inspection
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
