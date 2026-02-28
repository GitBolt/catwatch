export const ALL_ZONES = [
  "boom_arm",
  "bucket",
  "cab",
  "cooling",
  "drivetrain",
  "engine",
  "hydraulics",
  "steps_handrails",
  "stick",
  "structural",
  "tires_rims",
  "tracks_left",
  "tracks_right",
  "undercarriage",
  "attachments",
] as const;

export type ZoneId = (typeof ALL_ZONES)[number];

export const ZONE_LABELS: Record<ZoneId, string> = {
  boom_arm: "Boom Arm",
  bucket: "Bucket",
  cab: "Cab",
  cooling: "Cooling",
  drivetrain: "Drivetrain",
  engine: "Engine",
  hydraulics: "Hydraulics",
  steps_handrails: "Steps & Handrails",
  stick: "Stick",
  structural: "Structural",
  tires_rims: "Tires & Rims",
  tracks_left: "Tracks (Left)",
  tracks_right: "Tracks (Right)",
  undercarriage: "Undercarriage",
  attachments: "Attachments",
};

export const SEVERITY_COLORS = {
  GREEN: { bg: "rgba(34,197,94,0.12)", border: "#22c55e", text: "#4ade80", fill: "#22c55e" },
  YELLOW: { bg: "rgba(234,179,8,0.12)", border: "#eab308", text: "#facc15", fill: "#eab308" },
  RED: { bg: "rgba(239,68,68,0.12)", border: "#ef4444", text: "#f87171", fill: "#ef4444" },
  GRAY: { bg: "rgba(107,114,128,0.12)", border: "#6b7280", text: "#9ca3af", fill: "#6b7280" },
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;
