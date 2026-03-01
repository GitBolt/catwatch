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

/** Search terms by zone — used to build parts.cat.com search URLs for 797F */
export const ZONE_PART_NUMBERS: Record<ZoneId, string> = {
  tires_rims: "797F tires rims wheels",
  dump_body: "797F dump body truck box",
  hoist_cylinders: "797F hoist cylinders",
  suspension: "797F suspension cylinders",
  engine: "797F engine components",
  cooling: "797F radiator cooling system",
  drivetrain: "797F drivetrain transmission",
  brakes: "797F brake components",
  cab: "797F cab windshield ROPS",
  steps_handrails: "797F steps handrails",
  frame: "797F frame chassis",
  hydraulics: "797F hydraulic components",
  exhaust: "797F exhaust system",
};

export const CAT_PARTS_SEARCH_URL = "https://parts.cat.com/en/catcorp/search";

export function getPartSearchUrl(searchTerm: string): string {
  return `${CAT_PARTS_SEARCH_URL}?q=${encodeURIComponent(searchTerm)}`;
}

export const SEVERITY_COLORS = {
  GREEN: { bg: "rgba(106,158,114,0.10)", border: "#6a9e72", text: "#82b88a", fill: "#6a9e72" },
  YELLOW: { bg: "rgba(176,147,64,0.10)", border: "#b09340", text: "#cdb460", fill: "#b09340" },
  RED: { bg: "rgba(184,92,92,0.10)", border: "#b85c5c", text: "#d08080", fill: "#b85c5c" },
  GRAY: { bg: "rgba(107,100,94,0.10)", border: "#6b645e", text: "#8a837c", fill: "#6b645e" },
} as const;

export type Severity = keyof typeof SEVERITY_COLORS;
