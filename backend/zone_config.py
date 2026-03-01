# Zone configuration for CAT 797F mining haul truck inspection
# Regions are normalized (x1, y1, x2, y2) for a side-view perspective

ZONE_REGIONS = {
    "tires_rims":      (0.0,  0.55, 1.0,  1.0),   # all 6 tires along the bottom
    "dump_body":       (0.25, 0.0,  0.95, 0.45),   # massive dump body upper half
    "hoist_cylinders": (0.55, 0.25, 0.8,  0.65),   # hoist cylinders connecting body to frame
    "suspension":      (0.0,  0.45, 1.0,  0.7),    # struts near tire areas
    "engine":          (0.0,  0.15, 0.3,  0.55),   # C175-20 diesel front center
    "cooling":         (0.0,  0.05, 0.2,  0.45),   # radiator / V-grille front face
    "drivetrain":      (0.2,  0.5,  0.7,  0.8),    # transmission, torque converter center bottom
    "brakes":          (0.0,  0.6,  1.0,  0.9),    # wet disc brakes near wheels
    "cab":             (0.0,  0.0,  0.25, 0.45),   # operator cab front upper left
    "steps_handrails": (0.0,  0.25, 0.15, 0.7),    # access ladders on left side
    "frame":           (0.1,  0.3,  0.9,  0.65),   # main frame rails, cross members
    "hydraulics":      (0.15, 0.2,  0.85, 0.65),   # steering + hoist hydraulic lines throughout
    "exhaust":         (0.1,  0.0,  0.3,  0.25),   # dual exhaust stacks top center-left
}

ZONE_PROMPT_MAP = {
    "tires_rims":      "tires_rims_prompt",
    "dump_body":       "dump_body_prompt",
    "hoist_cylinders": "hoist_cylinders_prompt",
    "suspension":      "suspension_prompt",
    "engine":          "engine_system_prompt",
    "cooling":         "engine_coolant_prompt",
    "drivetrain":      "drivetrain_prompt",
    "brakes":          "brakes_prompt",
    "cab":             "cab_glass_mirrors_prompt",
    "steps_handrails": "steps_handrails_prompt",
    "frame":           "structural_integrity_prompt",
    "hydraulics":      "hydraulic_system_prompt",
    "exhaust":         "exhaust_prompt",
}

LABEL_TO_ZONE = {
    # ── CAT 797F YOLO detection labels ────────────────────────────────────
    "tire":                "tires_rims",
    "rim":                 "tires_rims",
    "wheel":               "tires_rims",
    "lug_nut":             "tires_rims",
    "dump_body":           "dump_body",
    "tailgate":            "dump_body",
    "liner":               "dump_body",
    "hoist_cylinder":      "hoist_cylinders",
    "hoist_pin":           "hoist_cylinders",
    "suspension_strut":    "suspension",
    "strut":               "suspension",
    "engine_compartment":  "engine",
    "engine":              "engine",
    "turbocharger":        "engine",
    "radiator":            "cooling",
    "fan_shroud":          "cooling",
    "coolant_line":        "cooling",
    "transmission":        "drivetrain",
    "torque_converter":    "drivetrain",
    "final_drive":         "drivetrain",
    "axle":                "drivetrain",
    "brake_disc":          "brakes",
    "brake_line":          "brakes",
    "brake_caliper":       "brakes",
    "cab":                 "cab",
    "cab_glass":           "cab",
    "windshield":          "cab",
    "mirror":              "cab",
    "step":                "steps_handrails",
    "handrail":            "steps_handrails",
    "ladder":              "steps_handrails",
    "frame_rail":          "frame",
    "cross_member":        "frame",
    "weld":                "frame",
    "hydraulic_hose":      "hydraulics",
    "hydraulic_cylinder":  "hydraulics",
    "steering_cylinder":   "hydraulics",
    "exhaust":             "exhaust",
    "exhaust_stack":       "exhaust",
    "muffler":             "exhaust",
    "mining_truck":        "frame",

    # ── Loose synonyms (legacy or third-party label compatibility) ────────
    "hydraulic hose":      "hydraulics",
    "hydraulic cylinder":  "hydraulics",
    "hose":                "hydraulics",
    "hoist cylinder":      "hoist_cylinders",
    "dump body":           "dump_body",
    "brake disc":          "brakes",
    "brake line":          "brakes",
    "suspension strut":    "suspension",
    "frame rail":          "frame",
    "cross member":        "frame",
    "exhaust stack":       "exhaust",
    "engine compartment":  "engine",
    "coolant":             "cooling",
    "structural member":   "frame",
    "attachment":          "dump_body",
}

ALL_ZONES = list(ZONE_REGIONS.keys())

_LABEL_KEYS_BY_LEN = sorted(LABEL_TO_ZONE.keys(), key=len, reverse=True)


def zone_from_label(label):
    """Map a detection label to a zone ID using substring matching.
    Tries exact match first, then longest substring match."""
    low = label.lower().strip()
    if low in LABEL_TO_ZONE:
        return LABEL_TO_ZONE[low]
    for key in _LABEL_KEYS_BY_LEN:
        if key in low:
            return LABEL_TO_ZONE[key]
    return None


def zone_from_bbox(bbox):
    """Given a normalized (x1, y1, x2, y2) bbox, return the zone whose region
    contains the bbox center. Returns None if no zone matches."""
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0

    best_zone = None
    best_area = float("inf")

    for zone_id, (rx1, ry1, rx2, ry2) in ZONE_REGIONS.items():
        if rx1 <= cx <= rx2 and ry1 <= cy <= ry2:
            area = (rx2 - rx1) * (ry2 - ry1)
            if area < best_area:
                best_area = area
                best_zone = zone_id

    return best_zone
