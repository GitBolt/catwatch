"""
Download trained YOLO weights from Modal volume after training completes.

Usage:
    python scripts/get_trained_model.py
"""

import subprocess
import sys
from pathlib import Path

VOLUME = "dronecat-models"
FILES = ["dronecat_yolo_best.pt", "dronecat_yolo_last.pt", "classes.json"]

weights_dir = Path(__file__).resolve().parent.parent / "backend" / "modal_app" / "weights"
weights_dir.mkdir(exist_ok=True)

print(f"Downloading trained model weights to {weights_dir}/\n")

any_downloaded = False
for filename in FILES:
    dest = weights_dir / filename
    print(f"  {filename} ... ", end="", flush=True)
    result = subprocess.run(
        ["modal", "volume", "get", VOLUME, filename, str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        size_kb = dest.stat().st_size // 1024
        print(f"ok ({size_kb} KB)")
        any_downloaded = True
    else:
        print(f"not found (skipping)")

if not any_downloaded:
    print("\nNo files downloaded. Has training completed?")
    print("Run: modal run backend/modal_app/train_yolo.py")
    sys.exit(1)

print(f"\nDone. Redeploy to activate the new model:")
print("  modal deploy backend/modal_app/orchestrator.py")
