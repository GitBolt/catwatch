#!/usr/bin/env python3
"""Validate that each HackIL26-CATrack sample image maps to the expected
zone and sub-section prompt. Run before demo to catch routing errors."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.zone_config import ZONE_PROMPT_MAP

EXPECTED_MAPPINGS = [
    ("Pass/HydraulicHose.jpg",                    "hydraulics",      "GREEN",       "hydraulic_system_prompt"),
    ("Pass/HydraulicFluidFiltrationSystem.jpg",    "hydraulics",      "GREEN",       "hydraulic_system_prompt"),
    ("Pass/HydraulicFluidTank.jpg",                "hydraulics",      "GREEN",       "hydraulic_system_prompt"),
    ("Pass/CoolantReservoir.jpg",                  "cooling",         "GREEN",       "engine_coolant_prompt"),
    ("Pass/CoolingSystemHose.jpg",                 "cooling",         "YELLOW",      "engine_coolant_prompt"),
    ("Pass/GoodStep.jpg",                          "steps_handrails", "YELLOW",      "steps_handrails_prompt"),
    ("Pass/HousingSeal.jpg",                       "structural",      "GREEN",       "structural_integrity_prompt"),
    ("Pass/BrokenRimBolt1.jpg",                    "tires_rims",      "RED",         "tires_rims_prompt"),
    ("Pass/BrokenRimBolt2.jpg",                    "tires_rims",      "RED",         "tires_rims_prompt"),
    ("Fail/DamagedAccessLadder.jpg",               "steps_handrails", "RED",         "steps_handrails_prompt"),
    ("Fail/HydraulicFluidFiltration.jpg",          "hydraulics",      "YELLOW/RED",  "hydraulic_system_prompt"),
    ("Fail/RustOnHydraulicComponentBracket.jpg",   "structural",      "YELLOW",      "structural_integrity_prompt"),
    ("Fail/StructuralDamage.jpg",                  "structural",      "RED",         "structural_integrity_prompt"),
    ("Fail/Tire ShowsSignsUnevenWear.jpg",         "tires_rims",      "YELLOW",      "tires_rims_prompt"),
]


def main():
    passed = 0
    failed = 0

    print("Validating ZONE_PROMPT_MAP routing against HackIL26-CATrack samples")
    print("=" * 70)

    for image, zone, expected_rating, expected_prompt in EXPECTED_MAPPINGS:
        actual_prompt = ZONE_PROMPT_MAP.get(zone)
        ok = actual_prompt == expected_prompt

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"  [{status}] {image:45s} zone={zone:20s} prompt={actual_prompt}")
        if not ok:
            print(f"         EXPECTED prompt={expected_prompt}")

    print()
    print(f"Results: {passed} passed, {failed} failed out of {len(EXPECTED_MAPPINGS)}")

    if failed:
        print("FIX ZONE_PROMPT_MAP BEFORE DEMO — wrong prompt = wrong findings!")
        sys.exit(1)
    else:
        print("All zone->prompt mappings validated.")


if __name__ == "__main__":
    main()
