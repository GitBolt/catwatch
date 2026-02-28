#!/usr/bin/env python3
"""Run all tests that need no API keys or Modal. From repo root: python3 scripts/run_local_tests.py"""

import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)


def test_zone_config():
    from backend.zone_config import ZONE_REGIONS, ZONE_PROMPT_MAP, zone_from_bbox, zone_from_label, LABEL_TO_ZONE

    assert len(ZONE_REGIONS) == 15
    assert zone_from_bbox([0.5, 0.3, 0.6, 0.4]) in ZONE_REGIONS
    assert ZONE_PROMPT_MAP.get("hydraulics") == "hydraulic_system_prompt"
    assert zone_from_label("hydraulic hose") == "hydraulics"
    assert zone_from_label("track chain") == "undercarriage"
    assert zone_from_label("bucket teeth") == "bucket"
    assert zone_from_label("boom arm") == "boom_arm"
    assert zone_from_label("unknown thing") is None
    assert len(LABEL_TO_ZONE) > 20
    print("  zone_config OK")


def test_nlp():
    from backend.nlp import extract_finding

    r = extract_finding("hydraulic hose active seep at boom pivot")
    assert r["zone"] == "hydraulics" and r["rating"] == "RED"
    r = extract_finding("bucket cutting edge good, pins tight")
    assert r["zone"] == "bucket" and r["rating"] == "GREEN"
    print("  nlp OK")


def test_prompts():
    from backend.prompts import (
        BRIEF_PROMPT, SPEC_PROMPT, REPORT_PROMPT,
        CAT_INSPECTION_PERSONA, VLM_OUTPUT_SCHEMA,
        get_sub_section_prompt,
    )

    assert "{zone}" in BRIEF_PROMPT and "{hours}" in BRIEF_PROMPT
    assert "step" in get_sub_section_prompt("steps_handrails_prompt").lower()
    assert "callout" in VLM_OUTPUT_SCHEMA
    assert "CAT 325" in CAT_INSPECTION_PERSONA
    print("  prompts OK")


def test_data_files():
    import json

    with open("data/cat_spec_kb.json") as f:
        kb = json.load(f)
    assert "hydraulics" in kb and "undercarriage" in kb

    with open("data/seed_inspections.json") as f:
        insp = json.load(f)
    assert len(insp["inspections"]) >= 1 and "unit" in insp

    with open("data/seed_parts.json") as f:
        parts = json.load(f)
    assert parts.get("data_type") == "test" and len(parts["parts"]) >= 2
    print("  data files OK")


def test_validate_zones():
    from scripts.validate_zones import EXPECTED_MAPPINGS
    from backend.zone_config import ZONE_PROMPT_MAP

    for _img, zone, _rating, expected_prompt in EXPECTED_MAPPINGS:
        assert ZONE_PROMPT_MAP.get(zone) == expected_prompt
    print("  zone->prompt mapping OK")


def main():
    print("Local tests (no Modal, no API keys)\n")
    test_zone_config()
    test_nlp()
    test_prompts()
    test_data_files()
    test_validate_zones()
    print("\nAll local tests passed.")


if __name__ == "__main__":
    main()
