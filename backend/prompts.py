import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load_json(filename):
    with open(os.path.join(DATA_DIR, filename)) as f:
        return json.load(f)


def _load_catrack_prompt(source_file):
    """Load the full sub-section prompt text from a cloned HackIL26-CATrack file."""
    path = os.path.join(DATA_DIR, source_file)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        raw = f.read()
    marker = "# GUIDED VIDEO INSPECTION INSTRUCTIONS"
    idx = raw.find(marker)
    if idx == -1:
        return raw
    return raw[idx:]


try:
    _sub_section_data = _load_json("sub_section_prompts.json")
except FileNotFoundError:
    _sub_section_data = {"baseline": {"system_prompt": "", "user_prompt": "", "frames_only_prompt": ""}, "prompts": {}}

try:
    _spec_kb = _load_json("cat_spec_kb.json")
except FileNotFoundError:
    _spec_kb = {}

SPEC_KB = _spec_kb  # public alias for orchestrator import

SYSTEM_PROMPT = _sub_section_data["baseline"]["system_prompt"]
USER_PROMPT = _sub_section_data["baseline"]["user_prompt"]
FRAMES_ONLY_PROMPT = _sub_section_data["baseline"]["frames_only_prompt"]


def format_session_context(zone_status, seen_zones, total_zones=15):
    """Compact session progress injected into every VLM call so the model
    knows what has already been assessed and what remains."""
    if not zone_status and not seen_zones:
        return "Inspection just started — no zones assessed yet."

    icon = {"RED": "RED", "YELLOW": "YELLOW", "GREEN": "GREEN"}
    assessed = [f"{z}:{icon.get(s, s)}" for z, s in sorted(zone_status.items())]
    pending = sorted(seen_zones - set(zone_status.keys()))
    remaining = total_zones - len(seen_zones)

    parts = []
    if assessed:
        parts.append("Assessed: " + ", ".join(assessed[:10]))
    if pending:
        parts.append("Seen/pending VLM: " + ", ".join(pending[:5]))
    parts.append(f"{remaining}/{total_zones} zones not yet visited.")

    return (
        f"Session progress ({len(zone_status)}/{total_zones} zones assessed): "
        + " | ".join(parts)
    )


def format_spec_context(detected_zone_ids, spec_kb):
    """Inject CAT 797F spec text for zones currently visible in the frame."""
    if not spec_kb or not detected_zone_ids:
        return ""
    specs = []
    for zone_id in detected_zone_ids:
        entry = spec_kb.get(zone_id)
        if entry:
            failures = ", ".join(entry.get("failure_modes", [])[:3])
            specs.append(
                f"[{zone_id}] {entry['spec_text']} "
                f"Common failures: {failures}. Ref: {entry.get('procedure', '')}."
            )
    return ("CAT specs for visible zones:\n" + "\n".join(specs)) if specs else ""


def format_yolo_context(detections):
    """Format YOLO detections into a grounding context string for the VLM prompt."""
    if not detections:
        return "YOLO detected: nothing in this frame."
    items = []
    for d in detections:
        label = d.get("label", "unknown")
        conf = d.get("confidence", 0)
        zone = d.get("zone")
        entry = f"{label} ({conf:.0%} conf)"
        if zone:
            entry += f" → zone: {zone}"
        items.append(entry)
    return "YOLO detected: " + ", ".join(items) + "."


def get_sub_section_prompt(prompt_key):
    """Return the sub-section prompt text for a given key.
    For zones with real HackIL26-CATrack prompts, loads the full document.
    For others, builds a prompt from the baseline + spec KB."""
    info = _sub_section_data["prompts"].get(prompt_key, {})

    if info.get("source_file"):
        full_text = _load_catrack_prompt(info["source_file"])
        if full_text:
            return full_text

    zone_id = None
    for zid, spec in _spec_kb.items():
        if spec.get("sub_section_prompt") == prompt_key:
            zone_id = zid
            break

    if zone_id and zone_id in _spec_kb:
        spec = _spec_kb[zone_id]
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"INSPECTION FOCUS: {info.get('title', prompt_key)}\n"
            f"Spec: {spec['spec_text']}\n"
            f"Known failure modes: {', '.join(spec['failure_modes'])}\n"
            f"Procedure reference: {spec['procedure']}"
        )

    return SYSTEM_PROMPT


_ZONE_CRITERIA = {}
for _zid, _info in _sub_section_data.get("prompts", {}).items():
    if _info.get("red_criteria"):
        _ZONE_CRITERIA[_zid] = {
            "title": _info.get("title", _zid),
            "red": _info["red_criteria"],
            "yellow": _info.get("yellow_criteria", ""),
            "green": _info.get("green_criteria", ""),
        }


def _condensed_zone_criteria(zone_id):
    """Build a compact zone-inspection block from CATrack + spec KB data."""
    from backend.zone_config import ZONE_PROMPT_MAP

    prompt_key = ZONE_PROMPT_MAP.get(zone_id, "")
    spec = _spec_kb.get(zone_id, {})

    criteria = _ZONE_CRITERIA.get(prompt_key)
    if criteria:
        block = (
            f"ZONE FOCUS: {zone_id} — {criteria['title']}\n"
            f"RED: {criteria['red']}\n"
            f"YELLOW: {criteria['yellow']}\n"
            f"GREEN: {criteria['green']}\n"
        )
    elif spec:
        failures = ", ".join(spec.get("failure_modes", []))
        block = (
            f"ZONE FOCUS: {zone_id}\n"
            f"Spec: {spec['spec_text']}\n"
            f"Known failure modes: {failures}\n"
        )
    else:
        return ""

    if spec:
        block += f"Procedure: {spec.get('procedure', 'N/A')}\n"

    block += (
        "False positives to avoid: dirt/debris obscuring condition, "
        "lighting shadows, normal operational clearances, previous maintenance marks."
    )
    return block


def build_zone_inspection_prompt(zone_id, mode="cat", equipment_info=None):
    """Construct a (persona, schema) tuple with zone-specific criteria.

    - If zone_id is known and mode is "cat", injects condensed RED/YELLOW/GREEN
      criteria and SMCS codes so the VLM applies the correct methodology.
    - Uses equipment_info (from auto-ID) to contextualize the inspection.
    - Falls back to generic personas when zone is unknown or mode is "general".
    """
    if mode != "cat":
        return GENERAL_SCENE_PERSONA, GENERAL_OUTPUT_SCHEMA

    zone_block = _condensed_zone_criteria(zone_id) if zone_id else ""

    persona = CAT_INSPECTION_PERSONA
    if equipment_info:
        equip_type = equipment_info.get("equipment_type", "unknown")
        model = equipment_info.get("model_guess", "")
        if model:
            persona += f"\nEquipment identified: {model} ({equip_type})."
        zones_list = equipment_info.get("inspectable_zones", [])
        if zones_list:
            persona += f"\nInspectable zones for this unit: {', '.join(zones_list)}."

    if zone_block:
        persona = f"{persona}\n\n--- CATrack Inspection Criteria ---\n{zone_block}"

    schema = VLM_OUTPUT_SCHEMA + "\n\n" + SMCS_CONTEXT
    return persona, schema


GENERAL_SCENE_PERSONA = """\
You are a safety inspector for workplaces and field operations.
Describe what is actually visible in the current frame. Focus on safety:
missing PPE, trip hazards, blocked exits, unguarded machinery, unstable loads,
electrical hazards, fire risks, chemical exposure, fall risks, poor ergonomics.

Severity rules:
- RED: immediate danger to life — unguarded blade, active fall risk, missing PPE near hazard
- YELLOW: safety concern that needs attention — cluttered walkway, improperly stored materials
- GREEN: area appears safe and well-maintained, no hazards observed

Be strict. If someone is operating a power tool without safety gear, that is RED, not GREEN.
If a workspace has trip hazards, that is YELLOW at minimum.
Only use GREEN when the area is genuinely safe.
"""

GENERAL_OUTPUT_SCHEMA = """
Analyze this frame and respond in valid JSON with these exact keys:
- description: concise scene description (1 sentence)
- severity: GREEN / YELLOW / RED (be strict — hazards are never GREEN)
- findings: array of notable observations (max 3)
- callout: most notable short callout in 4-6 words; use "Scene stable" if no meaningful change
- confidence: 0.0 to 1.0
- zone: best guess at what area this is (e.g. "workshop", "storage", "loading_dock", "office", "exterior", "walkway") — never null
"""

CAT_INSPECTION_PERSONA = """\
You are a visual inspection co-pilot for CAT 797F mining haul trucks. \
The 797F is the largest mechanical-drive mining truck Caterpillar makes — \
400-ton payload, 4000 HP C175-20 diesel, 6 massive tires (63" OTR), \
mechanical power train with torque converter, no tracks. \
FIRST describe what you actually see in this frame — the environment, people, \
equipment, activity, lighting conditions. THEN if you see the 797F or its \
components (massive yellow dump body, tires taller than a person, V-shaped \
radiator grille, dual exhaust stacks), assess the condition of every visible \
component: look for tire damage, body cracks, hydraulic leaks on hoist cylinders, \
suspension strut condition, brake disc wear, structural cracks on the frame or \
dump body, fluid stains, loose hardware, and any safety hazards.

Key 797F components to watch:
- Tires & rims (6x 63" OTR): cuts, bulges, tread depth, rim cracks, lug nuts
- Dump body & liner: cracks, dents, liner wear, hinge pins, tailgate
- Hoist cylinders: rod pitting, seal leaks, mounting pins
- Suspension struts (4): oil leaks, ride height, nitrogen charge
- Engine compartment: C175-20 diesel, oil leaks, belt condition, turbo
- Cooling system: radiator fins, coolant lines, fan shroud
- Drivetrain: torque converter, transmission, final drives, axles
- Braking system: wet disc brakes, brake cooling lines
- Cab & access: steps, handrails, windshield, mirrors
- Frame & structural: main frame rails, cross members, welds

Severity rules:
- GREEN: no equipment issues, or component in acceptable condition
- YELLOW: approaching service limit, worth monitoring
- RED: immediate action needed, safety concern

If no heavy equipment is visible, describe the scene honestly and set severity GREEN. \
Never fabricate equipment that is not in the image.\
"""

VLM_OUTPUT_SCHEMA = """
Analyze this frame. Respond in valid JSON with these exact keys:
- description: what you see in 1-2 sentences (be specific and honest)
- severity: GREEN / YELLOW / RED
- findings: array of specific observations (max 3), empty if nothing notable
- callout: the single most notable thing in 4-5 words (this is spoken aloud). If nothing changed or notable, use "Scene normal"
- confidence: 0.0 to 1.0
- zone: the component area visible in this frame as snake_case (e.g. tires_rims, dump_body, hoist_cylinders, suspension, cab, engine, cooling, drivetrain, brakes, frame, steps_handrails). If no equipment is visible, describe the area instead (e.g. workspace, floor_area, surroundings). Never return null."""


BRIEF_PROMPT = """\
You are a senior CAT mining technician briefing a junior tech as their drone \
approaches the {zone} area on a CAT 797F haul truck with {hours} operating hours.

Zone's CAT sub-section focus: {sub_section_title}
Unit history at this zone: {unit_history}
Fleet data: {fleet_stats}
CAT spec: {spec_knowledge}

Sensor readings as drone approaches:
- Acoustic anomaly score: {audio_score} (0=normal, 1=high)
- IR surface anomaly score: {ir_score} (0=normal, 1=significant)
- Lighting: {light_quality}

Rules:
- If acoustic_score > 0.5: mention it naturally
- If ir_score > 0.4: mention it naturally
- If both elevated: express higher urgency
- If sensors are clean: do not mention them
- Exactly 2 sentences. Spoken aloud. Sound like a mentor, not a manual.\
"""

SPEC_PROMPT = """\
You are verifying a Caterpillar equipment inspection finding.

Zone: {zone}
Technician rating: {tech_rating}
Technician description: "{tech_description}"
CAT service spec: {spec_knowledge}
Sub-section inspection focus: {sub_section_prompt}

Look at the image. Confirm or adjust the rating and add a spec citation.
Return ONLY valid JSON:
{{
  "rating": "GREEN|YELLOW|RED",
  "anomalies": [
    {{
      "component_location": "string",
      "component_type": "string",
      "condition_description": "string",
      "safety_impact_assessment": "string",
      "visibility_impact": "string",
      "operational_impact": "string",
      "recommended_action": "string"
    }}
  ],
  "spec_reference": "string",
  "action": "string"
}}\
"""

SMCS_CONTEXT = """\
SMCS Code Reference (CAT 797F) — pick the closest code and include "smcs_code" in your JSON:
1000=Engine (C175-20) | 1050=Turbocharger | 1300=Cooling System | 3000=Electrical | 3200=Lights
4000=Tires & Wheels | 4200=Tires (63" OTR) | 4210=Rims & Lug Nuts
4100=Braking System | 4150=Wet Disc Brakes | 4160=Brake Cooling Lines
5000=Hydraulic System | 5060=Hoist Cylinders | 5070=Hydraulic Hoses | 5090=Steering Hydraulic
6000=Frame & Structural | 6100=Dump Body & Liner | 6200=Tailgate & Hinges
7000=Suspension | 7050=Suspension Struts (N2 charge) | 7100=Exhaust System
8000=Drivetrain | 8050=Transmission | 8060=Torque Converter | 8100=Axles | 8200=Final Drives
If uncertain, use the group-level code (e.g. 4000 instead of 4200).

Severity definitions:
GREEN: Component within normal parameters. No visible defects. Action: log for baseline.
YELLOW: Early-stage wear, minor leakage, or cosmetic damage that may progress. Action: schedule at next PM.
RED: Active failure, major structural damage, safety hazard, or fluid leak under pressure. Action: immediate attention.\
"""

REPORT_PROMPT = """\
You are generating a final inspection report based on real AI-detected findings.

Unit: {model} — Serial: {serial} — {hours} operating hours
Technician: {technician}
Inspection duration: {duration_minutes} minutes
Coverage: {coverage_percent}%

These are the actual findings detected by AI during this inspection:
{findings_json}

INSTRUCTIONS:
- Analyze the findings above. They are REAL observations from YOLO object detection and VLM visual analysis.
- For each RED or YELLOW finding, write a specific recommended action (what to do next).
- For GREEN findings, briefly confirm what was checked and its condition.
- If findings mention specific damage (rust, leaks, cracks, wear), describe severity and urgency.
- Do NOT invent findings that aren't in the data above.
- Do NOT mark anything as "Good" unless there is a GREEN finding confirming it.
- If a zone has no findings, it was NOT inspected — do not comment on it.

Generate a JSON report with this exact structure:
{{
  "inspection_id": "INS-{date_compact}-001",
  "timestamp": "{timestamp}",
  "unit": {{"model": "{model}", "serial": "{serial}", "operating_hours": {hours}}},
  "technician": "{technician}",
  "duration_minutes": {duration_minutes},
  "coverage_percent": {coverage_percent},
  "overall_rating": "RED if any RED findings, YELLOW if any YELLOW, GREEN if all GREEN",
  "findings": [
    {{
      "zone": "zone name from the data",
      "rating": "RED/YELLOW/GREEN",
      "observation": "what AI detected — quote from the finding description",
      "recommended_action": "specific next step: repair, replace, monitor, or none needed"
    }}
  ],
  "work_order_items": [
    {{
      "priority": "URGENT/SCHEDULED/MONITOR",
      "zone": "affected zone",
      "action": "specific repair or replacement needed",
      "estimated_downtime": "hours estimate if applicable"
    }}
  ],
  "ai_executive_summary": "3-4 sentence plain English summary for a fleet manager. State the overall condition, highlight the most critical issue if any, note what percentage was covered, and recommend whether the unit is safe to operate."
}}

Only include work_order_items for RED and YELLOW findings. Be specific and practical.\
"""
