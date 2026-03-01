#!/usr/bin/env python3
"""Pre-warm all Modal containers before demo.
Run with: modal run scripts/warmup.py"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.modal_app import app
from backend.modal_app.yolo_detector import YoloDetector
from backend.modal_app.qwen_vl import Qwen25VLInspector

DUMMY_IMG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    "nGP4z8BQDwAEgAF/pooBPQAAAABJRU5ErkJggg=="
)


@app.local_entrypoint()
def main():
    print("=" * 60)
    print("Dronecat — Container Warmup")
    print("=" * 60)
    print()

    t_total = time.time()

    print("[YOLO] Warming up on T4...")
    t0 = time.time()
    yolo = YoloDetector()
    result = yolo.detect.remote(DUMMY_IMG)
    print(f"  -> {result.get('count', 0)} detections in {time.time() - t0:.1f}s")
    print()

    print("[Qwen2-VL] Warming up on A100...")
    t0 = time.time()
    qwen = Qwen25VLInspector()
    result = qwen.zone_brief.remote("Say hello in one word.")
    print(f"  -> '{result[:50]}' in {time.time() - t0:.1f}s")

    print()
    print(f"All containers warm in {time.time() - t_total:.1f}s total")
    print("Ready for demo.")
