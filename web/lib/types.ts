export interface Detection {
  label: string;
  confidence: number;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2] normalized
  zone?: string;
  anomaly_score?: number;
}

export interface DetectionMessage {
  type: "detection";
  detections: Detection[];
  coverage: number;
  total_zones: number;
  mode: "general" | "cat";
  yolo_ms: number;
  frame_id: number;
  client_ts: number;
  server_ts: number;
}

export interface AnalysisData {
  description: string;
  severity: "GREEN" | "YELLOW" | "RED";
  findings: string[];
  callout: string;
  confidence: number;
  component: string | null;
  zone?: string | null;
}

export interface AnalysisMessage {
  type: "analysis";
  data: AnalysisData;
  triggered_by: "cadence" | "manual_request" | "tier2_flag";
  mode: "general" | "cat";
  frame_id: number;
  client_ts: number;
  server_ts: number;
}

export interface FindingData {
  zone: string;
  rating: "GREEN" | "YELLOW" | "RED";
  description: string;
  createdAt?: string;
  snapshot?: string;
}

export interface FindingMessage {
  type: "finding";
  data: FindingData;
}

export interface VoiceAnswerMessage {
  type: "voice_answer";
  text: string;
  mode: "general" | "cat";
}

export interface ZoneFirstSeenMessage {
  type: "zone_first_seen";
  zone: string;
}

export interface ReportMessage {
  type: "report";
  data: Record<string, unknown>;
}

export interface FrameMessage {
  type: "frame";
  data: string; // base64 JPEG
  frame_id: number;
}

export interface SessionStateMessage {
  type: "session_state";
  session_id: string;
  mode: string;
  zones_seen: number;
  active: boolean;
  unit_serial?: string | null;
  unit_model?: string | null;
  fleet_tag?: string | null;
  location?: string | null;
}

export interface ZoneBriefMessage {
  type: "zone_brief";
  zone: string;
  text: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export interface SessionEndedMessage {
  type: "session_ended";
  data: {
    session_id: string;
    zones_inspected: number;
    total_zones: number;
    coverage_pct: number;
    findings_count: number;
    mode: string;
  };
}

export interface TranscriptMessage {
  type: "transcript";
  text: string;
}

export interface EquipmentInfo {
  equipment_type: string;
  model_guess: string | null;
  visible_text: string | null;
  inspectable_zones: string[];
}

export interface EquipmentIdentifiedMessage {
  type: "equipment_identified";
  data: EquipmentInfo;
}

export interface InsightData {
  event: string;
  description: string;
  components: string[];
  evidence_keywords: string[];
  vlm_severity: "GREEN" | "YELLOW" | "RED";
}

export interface InsightMessage {
  type: "insight";
  data: InsightData;
}

export interface ZoneTrend {
  severity_counts: { RED: number; YELLOW: number; GREEN: number };
  confidence_avg: number;
  drift: "worsening" | "improving" | "stable" | "inconsistent";
  sample_count: number;
}

export interface ZoneTrendMessage {
  type: "zone_trend";
  zone: string;
  trend: ZoneTrend;
}

export type ServerMessage =
  | DetectionMessage
  | AnalysisMessage
  | FindingMessage
  | VoiceAnswerMessage
  | ZoneFirstSeenMessage
  | ReportMessage
  | FrameMessage
  | SessionStateMessage
  | ZoneBriefMessage
  | ErrorMessage
  | SessionEndedMessage
  | TranscriptMessage
  | EquipmentIdentifiedMessage
  | InsightMessage
  | ZoneTrendMessage;

// Session types for the dashboard
export interface SessionSummary {
  id: string;
  mode: string;
  status: string;
  createdAt: string;
  endedAt: string | null;
  zonesSeen: number;
  coveragePct: number;
  _count: {
    findings: number;
  };
}
