ZONE_REGIONS = {
    "undercarriage":   (0.0,  0.65, 1.0,  1.0),
    "tracks_left":     (0.0,  0.55, 0.2,  1.0),
    "tracks_right":    (0.8,  0.55, 1.0,  1.0),
    "boom_arm":        (0.3,  0.05, 0.85, 0.65),
    "stick":           (0.5,  0.05, 0.95, 0.55),
    "bucket":          (0.65, 0.05, 1.0,  0.5),
    "cab":             (0.0,  0.05, 0.35, 0.65),
    "engine":          (0.0,  0.1,  0.25, 0.55),
    "hydraulics":      (0.15, 0.15, 0.75, 0.7),
    "cooling":         (0.0,  0.05, 0.2,  0.4),
    "drivetrain":      (0.0,  0.4,  0.3,  0.75),
    "attachments":     (0.6,  0.1,  1.0,  0.6),
    "steps_handrails": (0.0,  0.3,  0.25, 0.75),
    "tires_rims":      (0.0,  0.55, 0.3,  1.0),
    "structural":      (0.1,  0.0,  0.9,  0.85),
}

ZONE_PROMPT_MAP = {
    "hydraulics":      "hydraulic_system_prompt",
    "cooling":         "engine_coolant_prompt",
    "steps_handrails": "steps_handrails_prompt",
    "tires_rims":      "tires_rims_prompt",
    "undercarriage":   "undercarriage_tracks_prompt",
    "tracks_left":     "undercarriage_tracks_prompt",
    "tracks_right":    "undercarriage_tracks_prompt",
    "boom_arm":        "boom_stick_prompt",
    "stick":           "boom_stick_prompt",
    "bucket":          "bucket_attachments_prompt",
    "attachments":     "bucket_attachments_prompt",
    "engine":          "engine_system_prompt",
    "cab":             "cab_glass_mirrors_prompt",
    "structural":      "structural_integrity_prompt",
    "drivetrain":      "drivetrain_prompt",
}

LABEL_TO_ZONE = {
    "hydraulic hose": "hydraulics",
    "hydraulic cylinder": "hydraulics",
    "hose": "hydraulics",
    "track chain": "undercarriage",
    "track roller": "undercarriage",
    "track": "undercarriage",
    "sprocket": "undercarriage",
    "roller": "undercarriage",
    "bucket teeth": "bucket",
    "bucket": "bucket",
    "cutting edge": "bucket",
    "teeth": "bucket",
    "boom arm": "boom_arm",
    "boom": "boom_arm",
    "stick": "stick",
    "cab": "cab",
    "windshield": "cab",
    "mirror": "cab",
    "engine compartment": "engine",
    "engine": "engine",
    "radiator": "cooling",
    "coolant": "cooling",
    "step": "steps_handrails",
    "handrail": "steps_handrails",
    "ladder": "steps_handrails",
    "tire": "tires_rims",
    "rim": "tires_rims",
    "wheel": "tires_rims",
    "frame": "structural",
    "weld": "structural",
    "structural member": "structural",
    "coupler": "attachments",
    "attachment": "attachments",
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
