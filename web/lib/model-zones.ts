import type { ZoneId } from "./constants";

/**
 * Maps each inspection zone to the mesh indices in cat797.glb that
 * represent that region. The GLB has 43 meshes named Object_0..Object_42
 * with no semantic names, so mapping was derived from bounding-box
 * centroids extracted via gltf-transform inspect.
 *
 * Coordinate system: X = left-right, Y = front(−) to rear(+), Z = up.
 * Front of truck (cab / engine) ≈ Y −27, rear (dump body hinge) ≈ Y +25.
 */
export const ZONE_MESH_INDICES: Record<ZoneId, number[]> = {
  tires_rims: [20, 21, 23, 24, 28],
  dump_body: [2, 3, 5, 10, 11, 26, 27],
  hoist_cylinders: [36, 37, 38],
  suspension: [4, 7, 14, 15],
  engine: [0, 1, 33, 34],
  cooling: [9, 30, 31],
  drivetrain: [6, 16, 18, 19],
  brakes: [35, 39],
  cab: [32, 42],
  steps_handrails: [8, 17],
  frame: [12, 13, 22, 25, 29],
  hydraulics: [41],
  exhaust: [40],
};

/** Reverse lookup: mesh index → zone (first match wins). */
export function meshIndexToZone(idx: number): ZoneId | null {
  for (const [zone, indices] of Object.entries(ZONE_MESH_INDICES)) {
    if (indices.includes(idx)) return zone as ZoneId;
  }
  return null;
}
