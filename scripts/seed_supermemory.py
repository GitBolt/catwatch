#!/usr/bin/env python3
"""Seed Supermemory with past inspections from seed_inspections.json.
Run once before demo to populate unit + fleet history."""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from backend.supermemory_client import add_memory

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "seed_inspections.json")


def main():
    with open(DATA_PATH) as f:
        data = json.load(f)

    serial = data["unit"]["serial"]
    fleet_tag = data["fleet_tag"]
    model = data["unit"]["model"]

    print(f"Seeding Supermemory for unit {serial} ({model})")
    print(f"Fleet tag: {fleet_tag}")
    print(f"Inspections to seed: {len(data['inspections'])}")
    print()

    for insp in data["inspections"]:
        insp_id = insp["inspection_id"]
        hours = insp["operating_hours"]
        ts = insp["timestamp"]

        for finding in insp["findings"]:
            content = (
                f"Inspection {insp_id} on {ts}: "
                f"{model} serial {serial} at {hours}h — "
                f"Zone={finding['zone']}, "
                f"Rating={finding['rating']}, "
                f"Description={finding['description']}"
            )

            tags = [serial, fleet_tag]
            custom_id = f"{insp_id}_{finding['zone']}"
            metadata = {
                "zone": finding["zone"],
                "rating": finding["rating"],
                "operating_hours": hours,
                "timestamp": ts,
                "model": model,
            }

            try:
                result = add_memory(content, tags, custom_id=custom_id, metadata=metadata)
                print(f"  [{insp_id}] {finding['zone']:20s} {finding['rating']:6s} -> {result.get('id', 'ok')}")
            except Exception as e:
                print(f"  [{insp_id}] {finding['zone']:20s} FAILED: {e}")

            time.sleep(0.2)

        print()

    fleet_stats = data.get("fleet_stats", {})
    if fleet_stats:
        content = (
            f"Fleet statistics for {model} ({data['fleet_size']} units): "
            + json.dumps(fleet_stats, indent=None)
        )
        try:
            result = add_memory(
                content,
                [fleet_tag],
                custom_id=f"fleet_stats_{model.replace(' ', '_')}",
                metadata={"type": "fleet_stats", "model": model},
            )
            print(f"Fleet stats seeded -> {result.get('id', 'ok')}")
        except Exception as e:
            print(f"Fleet stats FAILED: {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
