export const ALL_ZONES = [
  "tires_rims",
  "dump_body",
  "hoist_cylinders",
  "suspension",
  "engine",
  "cooling",
  "drivetrain",
  "brakes",
  "cab",
  "steps_handrails",
  "frame",
  "hydraulics",
  "exhaust",
] as const;

export type ZoneId = (typeof ALL_ZONES)[number];

export const ZONE_LABELS: Record<ZoneId, string> = {
  tires_rims: "Tires & Rims",
  dump_body: "Dump Body",
  hoist_cylinders: "Hoist Cylinders",
  suspension: "Suspension",
  engine: "Engine",
  cooling: "Cooling",
  drivetrain: "Drivetrain",
  brakes: "Brakes",
  cab: "Cab",
  steps_handrails: "Steps & Handrails",
  frame: "Frame",
  hydraulics: "Hydraulics",
  exhaust: "Exhaust",
};

/** Cat 797F part numbers by zone (from cat-scrape output) — used for parts.cat.com links */
export const ZONE_PART_NUMBERS: Record<ZoneId, string> = {
  tires_rims: "192-4744",      // Undercarriage: Hex Head Bolt
  dump_body: "217-4195",      // Structures: Hose
  hoist_cylinders: "4T-6788", // Filters: Hydraulic/Transmission Filter
  suspension: "156-5444",     // Undercarriage: Suspension Mounting Key
  engine: "597-1291",         // Engine: Governor Gasket
  cooling: "172-5718",        // Engine: Radiator Water Lines Gasket
  drivetrain: "343-4465",     // Drivetrain: Transmission Element
  brakes: "381-3629",         // Drivetrain: Brake Friction Disc
  cab: "204-2281",            // Cabs: Cable Strap
  steps_handrails: "425-2594", // Structures: Suspension Support Channel Plate
  frame: "519-7297",          // Structures: Spacer Plate
  hydraulics: "465-6502",     // Drivetrain: Hydraulic Oil Filter
  exhaust: "133-5953",        // Engine: Exhaust Manifold Shield
};

export const CAT_PARTS_SEARCH_URL = "https://parts.cat.com/en/catcorp/search";

export function getPartSearchUrl(partNumber: string): string {
  return `${CAT_PARTS_SEARCH_URL}?q=${encodeURIComponent(partNumber)}`;
}

export const SEVERITY_COLORS = {
  GREEN: { bg: "rgba(106,158,114,0.10)", border: "#6a9e72", text: "#82b88a", fill: "#6a9e72" },
  YELLOW: { bg: "rgba(176,147,64,0.10)", border: "#b09340", text: "#cdb460", fill: "#b09340" },
  RED: { bg: "rgba(184,92,92,0.10)", border: "#b85c5c", text: "#d08080", fill: "#b85c5c" },
  GRAY: { bg: "rgba(107,100,94,0.10)", border: "#6b645e", text: "#8a837c", fill: "#6b645e" },
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;
