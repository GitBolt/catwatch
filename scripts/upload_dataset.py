#!/usr/bin/env python3
"""
Upload the prepared component dataset to the Modal volume for training.

Usage:
    python scripts/upload_dataset.py
    python scripts/upload_dataset.py --dataset data/component_dataset
"""

import argparse
import subprocess
import sys
from pathlib import Path

VOLUME = "dronecat-models"
DEFAULT_DATASET = Path(__file__).resolve().parent.parent / "data" / "component_dataset"
REMOTE_PREFIX = "dataset"


def upload_dir(local_dir, remote_dir):
    """Upload a local directory to Modal volume using modal volume put."""
    local_dir = Path(local_dir)
    if not local_dir.exists():
        return 0

    count = 0
    for f in sorted(local_dir.rglob("*")):
        if f.is_dir():
            continue
        rel = f.relative_to(local_dir)
        remote_path = f"{remote_dir}/{rel}"
        result = subprocess.run(
            ["modal", "volume", "put", VOLUME, str(f), remote_path],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            count += 1
        else:
            print(f"  FAIL: {rel} — {result.stderr.strip()}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Upload training dataset to Modal volume")
    parser.add_argument("--dataset", type=str, default=str(DEFAULT_DATASET),
                        help=f"Path to prepared dataset (default: {DEFAULT_DATASET})")
    args = parser.parse_args()

    dataset_dir = Path(args.dataset)
    if not dataset_dir.exists():
        print(f"Dataset not found: {dataset_dir}")
        print(f"Run first: python scripts/prepare_training_data.py --roboflow")
        sys.exit(1)

    yaml_path = dataset_dir / "data.yaml"
    if not yaml_path.exists():
        print(f"No data.yaml found in {dataset_dir} — is this a valid dataset?")
        sys.exit(1)

    print(f"Uploading {dataset_dir} → modal volume '{VOLUME}' at /{REMOTE_PREFIX}/")
    print(f"This may take a few minutes for large datasets.\n")

    total = 0
    for split in ("train", "val"):
        for subdir in ("images", "labels"):
            local = dataset_dir / subdir / split
            remote = f"{REMOTE_PREFIX}/{subdir}/{split}"
            if local.exists():
                n_files = len(list(local.iterdir()))
                print(f"  {subdir}/{split}: {n_files} files... ", end="", flush=True)
                n = upload_dir(local, remote)
                print(f"uploaded {n}")
                total += n

    # Upload data.yaml and classes.json
    for meta_file in ("data.yaml", "classes.json"):
        local = dataset_dir / meta_file
        if local.exists():
            result = subprocess.run(
                ["modal", "volume", "put", VOLUME, str(local), f"{REMOTE_PREFIX}/{meta_file}"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                print(f"  {meta_file}: uploaded")
                total += 1

    print(f"\nDone. {total} files uploaded to volume '{VOLUME}'.")
    print(f"\nNext: modal run backend/modal_app/train_yolo.py")


if __name__ == "__main__":
    main()
