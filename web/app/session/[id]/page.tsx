"use client";

import { useParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { useSessionSocket } from "@/hooks/use-session-socket";
import { VideoCanvas } from "@/components/video-canvas";
import { DetectionOverlay } from "@/components/detection-overlay";
import { AnalysisPanel } from "@/components/analysis-panel";
import { ZonePanel } from "@/components/zone-panel";
import { FindingsList } from "@/components/findings-list";
import { VoiceButton } from "@/components/voice-button";
import { ReportDialog } from "@/components/report-dialog";
import { TopBar } from "@/components/top-bar";
import { UnitHistoryPanel } from "@/components/unit-history-panel";

export default function LiveSessionPage() {
  const { id } = useParams<{ id: string }>();
  const containerRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 960, height: 540 });

  const {
    connected,
    frame,
    detections,
    analysis,
    findings,
    zonesSeen,
    coverage,
    mode,
    yoloMs,
    report,
    unitSerial,
    unitModel,
    fleetTag,
    unitProfile,
    unitProfileLoading,
    send,
  } = useSessionSocket(id);

  const handleQuestion = useCallback(
    (text: string) => {
      send({ type: "voice_question", text });
    },
    [send],
  );

  const handleReport = useCallback(() => {
    send({ type: "generate_report", model: "CAT 325", coverage_percent: coverage });
  }, [send, coverage]);

  const handleModeChange = useCallback(
    (newMode: string) => {
      send({ type: "set_mode", mode: newMode });
    },
    [send],
  );

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
        totalZones={15}
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
          <ZonePanel zonesSeen={zonesSeen} coverage={coverage} />
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
        <VoiceButton onQuestion={handleQuestion} />
        <ReportDialog report={report} onGenerate={handleReport} />
      </div>
    </div>
  );
}
