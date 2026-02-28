import re

ZONE_KEYWORDS = {
    "hydraulic|hose|pump|filtration": "hydraulics",
    "track|undercarriage|sprocket|roller|link": "undercarriage",
    "bucket|cutting edge|teeth": "bucket",
    "boom arm|boom|stick": "boom_arm",
    "engine|oil level|belt|filter": "engine",
    "cab|seat|mirror|gauge|horn|windshield|glass": "cab",
    "cooling|coolant|radiator": "cooling",
    "step|ladder|handrail|railing": "steps_handrails",
    "tire|rim|lug|wheel|tread": "tires_rims",
    "structural|frame|weld|rust|corrosion": "structural",
}

RATING_MAP = {
    r"good|fine|okay|ok|normal|clean|pass|tight|secure|intact": "GREEN",
    r"worn|wear|watch|monitor|low|slightly|minor|getting|loose|borderline|overtension|undertension|uneven|approaching|progressing": "YELLOW",
    r"fail|bad|leak|crack|broken|damage|damaged|active|seep|drip|red|do not|missing": "RED",
}

NEGATION_PATTERN = re.compile(
    r"\b(no|not|without|don'?t|doesn'?t|isn'?t|aren'?t|none|zero)\b\s+\w*\s*",
    re.IGNORECASE,
)


def _strip_negated_phrases(text):
    """Remove simple negated phrases like 'no cracks', 'not damaged'
    so they don't trigger false positive ratings."""
    return NEGATION_PATTERN.sub(" ", text)


def extract_finding(transcript):
    """Parse a voice transcript into {zone, rating, description}.
    Returns the best-match zone and highest-severity rating found."""
    zone = None
    for pattern, zone_id in ZONE_KEYWORDS.items():
        if re.search(pattern, transcript, re.IGNORECASE):
            zone = zone_id
            break

    cleaned = _strip_negated_phrases(transcript)

    rating = "GREEN"
    severity_order = {"GREEN": 0, "YELLOW": 1, "RED": 2}
    for pattern, r in RATING_MAP.items():
        if re.search(pattern, cleaned, re.IGNORECASE):
            if severity_order.get(r, 0) > severity_order.get(rating, 0):
                rating = r

    return {"zone": zone, "rating": rating, "description": transcript.strip()}
