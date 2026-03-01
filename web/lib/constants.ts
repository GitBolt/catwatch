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
  GREEN: { bg: "rgba(106,158,114,0.10)", border: "#6a9e72", text: "#82b88a", fill: "#6a9e72" },
  YELLOW: { bg: "rgba(176,147,64,0.10)", border: "#b09340", text: "#cdb460", fill: "#b09340" },
  RED: { bg: "rgba(184,92,92,0.10)", border: "#b85c5c", text: "#d08080", fill: "#b85c5c" },
  GRAY: { bg: "rgba(107,100,94,0.10)", border: "#6b645e", text: "#8a837c", fill: "#6b645e" },
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;
