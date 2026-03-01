"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { useSessionSocket } from "@/hooks/use-session-socket";
import { VideoCanvas } from "@/components/video-canvas";
import { DetectionOverlay } from "@/components/detection-overlay";
import { AnalysisPanel } from "@/components/analysis-panel";
import { ZonePanel } from "@/components/zone-panel";
import { FindingsList } from "@/components/findings-list";
import { InsightsPanel } from "@/components/insights-panel";
import { VoiceButton } from "@/components/voice-button";
import { TopBar } from "@/components/top-bar";
import { UnitHistoryPanel } from "@/components/unit-history-panel";

export default function LiveSessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [canvasSize] = useState({ width: 960, height: 540 });
  const [confirmEnd, setConfirmEnd] = useState(false);

  const {
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
    equipmentInfo,
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
  } = useSessionSocket(id);

  const handleModeChange = useCallback(
    (newMode: string) => {
      send({ type: "set_mode", mode: newMode });
    },
    [send],
  );

  if (sessionEnded) {
    const s = sessionEnded;
    return (
      <div style={{ display: "flex", height: "100vh", alignItems: "center", justifyContent: "center", background: "var(--bg)", padding: 48 }}>
        <div style={{ maxWidth: 640, width: "100%", padding: "48px 56px", background: "var(--bg-card)", borderRadius: "var(--radius)", border: "1px solid var(--border)" }}>
          <h1 style={{ fontSize: 26, fontWeight: 700, marginBottom: 8, letterSpacing: "-0.02em" }}>
            Inspection Complete
          </h1>
          <p style={{ fontSize: 14, color: "var(--text-muted)", marginBottom: 40, lineHeight: 1.5 }}>
            Your inspection has been saved. View the full report with findings, coverage, and AI-generated summary.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 40 }}>
            <div className="card stat-card" style={{ padding: 24 }}>
              <div style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.zones_inspected}</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>of {s.total_zones} zones</div>
            </div>
            <div className="card stat-card" style={{ padding: 24 }}>
              <div style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.coverage_pct}%</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>coverage</div>
            </div>
            <div className="card stat-card" style={{ padding: 24 }}>
              <div style={{ fontSize: 32, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{s.findings_count}</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>findings</div>
            </div>
            <div className="card stat-card" style={{ padding: 24 }}>
              <div style={{ fontSize: 15, fontWeight: 600, textTransform: "uppercase", color: "var(--amber)" }}>{s.mode}</div>
              <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>mode</div>
            </div>
          </div>

          <div className="mono" style={{ fontSize: 12, color: "var(--text-dim)", marginBottom: 32, padding: "12px 16px", background: "var(--bg)", borderRadius: "var(--radius-sm)" }}>
            Session {s.session_id}
          </div>

          <div style={{ display: "flex", gap: 16 }}>
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

  const hasMemory = unitProfile !== null;

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        flexDirection: "column",
        gap: 6,
        background: "var(--bg)",
        padding: 10,
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

      <div style={{ display: "flex", minHeight: 0, flex: 1, gap: 10 }}>
        {/* Video + Overlay + Voice */}
        <div
          style={{
            position: "relative",
            flex: "1 1 0",
            minWidth: 0,
            overflow: "hidden",
            borderRadius: "var(--radius)",
            background: "var(--bg-card)",
          }}
        >
          <VideoCanvas
            frameRef={frameRef}
            width={canvasSize.width}
            height={canvasSize.height}
          />
          <DetectionOverlay
            detections={detections}
            width={canvasSize.width}
            height={canvasSize.height}
          />

          {!connected && !hasFrame && (
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

          {/* Voice button — bottom left */}
          <div style={{ position: "absolute", bottom: 16, left: 16, zIndex: 10 }}>
            <VoiceButton onAudio={sendAudio} voiceAnswer={voiceAnswer} />
          </div>

          {/* Voice answer overlay */}
          {voiceAnswer && (
            <div
              style={{
                position: "absolute",
                bottom: 72,
                left: 16,
                right: 16,
                background: "rgba(0,0,0,0.8)",
                backdropFilter: "blur(8px)",
                borderRadius: "var(--radius)",
                padding: "10px 14px",
                fontSize: 13,
                color: "var(--text)",
                lineHeight: 1.5,
                zIndex: 10,
                maxHeight: 120,
                overflow: "auto",
              }}
            >
              {voiceAnswer}
            </div>
          )}

          {/* End inspection — bottom right */}
          <div style={{ position: "absolute", bottom: 16, right: 16, zIndex: 10 }}>
            {confirmEnd ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6, background: "rgba(0,0,0,0.8)", backdropFilter: "blur(8px)", borderRadius: "var(--radius)", padding: "6px 10px" }}>
                <span style={{ fontSize: 12, color: "var(--text-muted)" }}>End?</span>
                <button onClick={() => { endSession(); setConfirmEnd(false); }} className="btn btn-danger btn-small">
                  Yes
                </button>
                <button onClick={() => setConfirmEnd(false)} className="btn btn-secondary btn-small">
                  No
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmEnd(true)}
                className="btn btn-small"
                style={{ background: "rgba(0,0,0,0.6)", backdropFilter: "blur(8px)", color: "var(--text-muted)", border: "1px solid rgba(255,255,255,0.1)" }}
              >
                End
              </button>
            )}
          </div>
        </div>

        {/* Right sidebar */}
        <div
          style={{
            display: "flex",
            width: 300,
            flexShrink: 0,
            flexDirection: "column",
            gap: 6,
            overflowY: "auto",
          }}
        >
          <UnitHistoryPanel
            unitSerial={unitSerial}
            unitModel={unitModel}
            fleetTag={fleetTag}
            location={location}
            memoryKey={memoryKey}
            profile={unitProfile}
            loading={unitProfileLoading}
          />
          <AnalysisPanel analysis={analysis} zoneTrends={zoneTrends} hasMemoryContext={hasMemory} />
          {insights.length > 0 && <InsightsPanel insights={insights} />}
          <ZonePanel zonesSeen={zonesSeen} coverage={coverage} totalZones={totalZones || 15} equipmentInfo={equipmentInfo} mode={mode} />
          <FindingsList findings={findings} hasMemoryContext={hasMemory} />
        </div>
      </div>
    </div>
  );
}
