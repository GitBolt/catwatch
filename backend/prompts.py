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


_sub_section_data = _load_json("sub_section_prompts.json")
_spec_kb = _load_json("cat_spec_kb.json")

SYSTEM_PROMPT = _sub_section_data["baseline"]["system_prompt"]
USER_PROMPT = _sub_section_data["baseline"]["user_prompt"]
FRAMES_ONLY_PROMPT = _sub_section_data["baseline"]["frames_only_prompt"]


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


BRIEF_PROMPT = """\
You are a senior CAT technician briefing a junior tech as their drone \
approaches the {zone} on a CAT 325 with {hours} operating hours.

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
You are verifying a CAT 325 TA-1 inspection finding.

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

REPORT_PROMPT = """\
You are generating a final TA-1 inspection report for a CAT 325.

Unit: {model} — Serial: {serial} — {hours} operating hours
Technician: {technician}
Inspection duration: {duration_minutes} minutes
Coverage: {coverage_percent}%

All zone findings:
{findings_json}

Work order draft:
{work_order_json}

Generate a JSON report with this exact structure:
{{
  "inspection_id": "INS-{date_compact}-001",
  "schema_version": "ta1_v2",
  "unit": {{"model": "{model}", "serial": "{serial}", "operating_hours": {hours}}},
  "technician": "{technician}",
  "timestamp": "{timestamp}",
  "duration_minutes": {duration_minutes},
  "coverage_percent": {coverage_percent},
  "findings": [... all zone findings with spec citations ...],
  "work_order_draft": [... parts to order ...],
  "ai_executive_summary": "2-3 sentence plain English summary for a manager"
}}

Be specific. Cite CAT procedure numbers. Prioritize RED findings first.\
"""
