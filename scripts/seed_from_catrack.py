#!/usr/bin/env python3
"""
Bootstrap YOLO training data from the CATrack sample images.

These 14 official Caterpillar inspection images are close-up, component-level
shots. This script creates bounding box labels for each (hand-mapped from
visual inspection), copies them into the training dataset, and applies
augmentation to multiply the 14 originals into ~150+ training samples.

Usage:
    python scripts/seed_from_catrack.py
    python scripts/seed_from_catrack.py --augment 12 --output data/component_dataset
"""

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CATRACK_DIR = PROJECT_ROOT / "data" / "catrack_samples"

COMPONENT_CLASSES = [
    "track_roller", "track_shoe", "sprocket", "idler", "track_chain",
    "final_drive", "hydraulic_hose", "hydraulic_cylinder", "bucket",
    "bucket_teeth", "cutting_edge", "boom", "stick", "cab", "cab_glass",
    "step", "handrail", "radiator", "engine_compartment", "exhaust",
    "tire", "rim", "coupler", "excavator",
]
CLS = {name: i for i, name in enumerate(COMPONENT_CLASSES)}

# Hand-labeled bounding boxes for each CATrack image.
# Format: list of (class_index, x_center, y_center, width, height) — all normalized.
# Derived from visual inspection of every image in the dataset.
LABELS = {
    # ── Fail images ───────────────────────────────────────────────────────
    "Fail/RustOnHydraulicComponentBracket.jpg": [
        (CLS["hydraulic_hose"],     0.38, 0.52, 0.10, 0.80),  # left corrugated hose
        (CLS["hydraulic_hose"],     0.55, 0.48, 0.10, 0.75),  # right corrugated hose
        (CLS["hydraulic_cylinder"], 0.72, 0.50, 0.20, 0.55),  # bracket/spring assembly right
    ],
    "Fail/CoolingSystemHose.jpg": [
        (CLS["engine_compartment"], 0.55, 0.55, 0.70, 0.70),  # engine bay area
        (CLS["hydraulic_hose"],     0.55, 0.78, 0.40, 0.22),  # yellow hose routing at bottom
        (CLS["radiator"],           0.42, 0.38, 0.22, 0.28),  # round silver component
    ],
    "Fail/DamagedAccessLadder.jpg": [
        (CLS["step"],               0.35, 0.72, 0.30, 0.35),  # damaged ladder/steps
        (CLS["hydraulic_cylinder"], 0.18, 0.50, 0.12, 0.55),  # cylinder rod left
        (CLS["tire"],               0.60, 0.50, 0.38, 0.72),  # large tire center-right
        (CLS["cab_glass"],          0.50, 0.18, 0.40, 0.30),  # cab windows top
    ],
    "Fail/StructuralDamage.jpg": [
        (CLS["step"],               0.42, 0.55, 0.35, 0.40),  # damaged step/ladder
        (CLS["cab_glass"],          0.48, 0.12, 0.50, 0.22),  # cab glass upper
        (CLS["hydraulic_hose"],     0.25, 0.32, 0.12, 0.22),  # hoses left side
        (CLS["cutting_edge"],       0.45, 0.92, 0.65, 0.12),  # bucket edge bottom
    ],
    "Fail/Tire ShowsSignsUnevenWear.jpg": [
        (CLS["tire"],               0.48, 0.62, 0.40, 0.65),  # main center tire
        (CLS["tire"],               0.15, 0.55, 0.28, 0.55),  # left tire
        (CLS["rim"],                0.48, 0.60, 0.22, 0.35),  # center rim
        (CLS["rim"],                0.15, 0.52, 0.15, 0.28),  # left rim
        (CLS["engine_compartment"], 0.55, 0.15, 0.50, 0.25),  # engine area top
    ],
    "Fail/HydraulicFluidFiltration.jpg": [
        (CLS["engine_compartment"], 0.50, 0.50, 0.85, 0.80),  # full engine bay
        (CLS["hydraulic_hose"],     0.35, 0.55, 0.20, 0.35),  # hoses center-left
        (CLS["radiator"],           0.65, 0.85, 0.30, 0.22),  # radiator grille bottom right
    ],

    # ── Pass images ───────────────────────────────────────────────────────
    "Pass/GoodStep.jpg": [
        (CLS["step"],               0.42, 0.58, 0.38, 0.55),  # 3-step assembly
        (CLS["tire"],               0.12, 0.42, 0.24, 0.60),  # tire left
        (CLS["handrail"],           0.68, 0.32, 0.08, 0.40),  # vertical rail right
    ],
    "Pass/HydraulicHose.jpg": [
        (CLS["hydraulic_hose"],     0.48, 0.28, 0.25, 0.35),  # hose bundle upper center
        (CLS["hydraulic_cylinder"], 0.45, 0.55, 0.15, 0.25),  # cylinder/linkage
        (CLS["tire"],               0.18, 0.45, 0.35, 0.70),  # large tire left
    ],
    "Pass/HousingSeal.jpg": [
        (CLS["radiator"],           0.50, 0.45, 0.70, 0.50),  # filter housing/seal center
        (CLS["engine_compartment"], 0.50, 0.85, 0.70, 0.20),  # lower engine area
    ],
    "Pass/BrokenRimBolt1.jpg": [
        (CLS["tire"],               0.50, 0.50, 0.95, 0.95),  # tire fills frame
        (CLS["rim"],                0.50, 0.52, 0.60, 0.65),  # rim center
    ],
    "Pass/BrokenRimBolt2.jpg": [
        (CLS["rim"],                0.50, 0.50, 0.90, 0.90),  # rim close-up fills frame
    ],
    "Pass/HydraulicFluidFiltrationSystem.jpg": [
        (CLS["engine_compartment"], 0.50, 0.50, 0.85, 0.80),  # full engine bay
        (CLS["hydraulic_hose"],     0.35, 0.55, 0.20, 0.35),  # hoses center-left
        (CLS["radiator"],           0.65, 0.85, 0.30, 0.22),  # radiator grille bottom right
    ],
    "Pass/HydraulicFluidTank.jpg": [
        (CLS["engine_compartment"], 0.50, 0.50, 0.90, 0.85),  # tank panel
    ],
    "Pass/CoolantReservoir.jpg": [
        (CLS["radiator"],           0.50, 0.35, 0.55, 0.45),  # coolant reservoir
        (CLS["hydraulic_hose"],     0.35, 0.42, 0.12, 0.40),  # black hose left
        (CLS["engine_compartment"], 0.50, 0.72, 0.80, 0.40),  # engine area lower
    ],
}


def write_yolo_label(path, annotations):
    lines = []
    for cls_id, cx, cy, w, h in annotations:
        lines.append(f"{cls_id} {cx:.4f} {cy:.4f} {w:.4f} {h:.4f}")
    path.write_text("\n".join(lines) + "\n")


def augment_image(img, labels, aug_idx):
    """Apply a deterministic augmentation based on aug_idx. Returns (img, labels)."""
    import cv2
    import numpy as np

    h, w = img.shape[:2]
    new_labels = list(labels)

    if aug_idx % 6 == 0:
        # Horizontal flip
        img = cv2.flip(img, 1)
        new_labels = [(c, 1.0 - cx, cy, bw, bh) for c, cx, cy, bw, bh in labels]
    elif aug_idx % 6 == 1:
        # Brightness increase
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] + random.randint(20, 50), 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    elif aug_idx % 6 == 2:
        # Brightness decrease
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[:, :, 2] = np.clip(hsv[:, :, 2] - random.randint(20, 50), 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    elif aug_idx % 6 == 3:
        # Saturation shift
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.int16)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] + random.randint(-30, 30), 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    elif aug_idx % 6 == 4:
        # Gaussian blur
        ksize = random.choice([3, 5, 7])
        img = cv2.GaussianBlur(img, (ksize, ksize), 0)
    elif aug_idx % 6 == 5:
        # Random crop (keep center 75-90%)
        scale = random.uniform(0.75, 0.90)
        new_w, new_h = int(w * scale), int(h * scale)
        x_off = random.randint(0, w - new_w)
        y_off = random.randint(0, h - new_h)
        img = img[y_off:y_off + new_h, x_off:x_off + new_w]
        # Adjust labels to new crop coordinates
        adjusted = []
        for c, cx, cy, bw, bh in labels:
            ncx = (cx * w - x_off) / new_w
            ncy = (cy * h - y_off) / new_h
            nbw = bw * w / new_w
            nbh = bh * h / new_h
            if 0.05 < ncx < 0.95 and 0.05 < ncy < 0.95:
                ncx = max(0.01, min(0.99, ncx))
                ncy = max(0.01, min(0.99, ncy))
                nbw = min(nbw, min(ncx, 1.0 - ncx) * 2)
                nbh = min(nbh, min(ncy, 1.0 - ncy) * 2)
                adjusted.append((c, ncx, ncy, nbw, nbh))
        new_labels = adjusted if adjusted else list(labels)
        img = cv2.resize(img, (w, h))

    return img, new_labels


def main():
    parser = argparse.ArgumentParser(description="Seed training data from CATrack samples")
    parser.add_argument("--output", type=str,
                        default=str(PROJECT_ROOT / "data" / "component_dataset"),
                        help="Output dataset directory")
    parser.add_argument("--augment", type=int, default=10,
                        help="Number of augmented copies per image (default: 10)")
    parser.add_argument("--val-ratio", type=float, default=0.2,
                        help="Fraction of originals to put in val split (default: 0.2)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    for split in ("train", "val"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    if not CATRACK_DIR.exists():
        print(f"CATrack samples not found at {CATRACK_DIR}")
        sys.exit(1)

    # Validate all images exist
    missing = []
    for rel_path in LABELS:
        if not (CATRACK_DIR / rel_path).exists():
            missing.append(rel_path)
    if missing:
        print(f"Missing images: {missing}")
        sys.exit(1)

    print(f"Seeding from {len(LABELS)} CATrack images → {output_dir}")
    print(f"Augmentations per image: {args.augment}")

    # Split originals into train/val
    all_keys = list(LABELS.keys())
    random.seed(42)
    random.shuffle(all_keys)
    n_val = max(1, int(len(all_keys) * args.val_ratio))
    val_keys = set(all_keys[:n_val])
    train_keys = set(all_keys[n_val:])

    print(f"Split: {len(train_keys)} train, {len(val_keys)} val (originals)")

    total_images = 0

    try:
        import cv2
        has_cv2 = True
    except ImportError:
        has_cv2 = False
        if args.augment > 0:
            print("WARNING: opencv-python not installed — skipping augmentation")
            print("  pip install opencv-python")

    for rel_path, annotations in LABELS.items():
        src_img = CATRACK_DIR / rel_path
        safe_name = rel_path.replace("/", "_").replace(" ", "_")
        stem = Path(safe_name).stem
        suffix = src_img.suffix

        split = "val" if rel_path in val_keys else "train"

        # Copy original
        dst_img = output_dir / "images" / split / f"catrack_{stem}{suffix}"
        dst_lbl = output_dir / "labels" / split / f"catrack_{stem}.txt"
        shutil.copy(src_img, dst_img)
        write_yolo_label(dst_lbl, annotations)
        total_images += 1

        n_annotations = len(annotations)
        class_names = [COMPONENT_CLASSES[a[0]] for a in annotations]
        print(f"  {rel_path:<50} → {split}  ({n_annotations} labels: {', '.join(class_names)})")

        # Augment (train only)
        if split == "train" and args.augment > 0 and has_cv2:
            img = cv2.imread(str(src_img))
            if img is None:
                continue
            for aug_i in range(args.augment):
                aug_img, aug_labels = augment_image(img, annotations, aug_i)
                aug_name = f"catrack_{stem}_aug{aug_i:02d}"
                aug_img_path = output_dir / "images" / "train" / f"{aug_name}{suffix}"
                aug_lbl_path = output_dir / "labels" / "train" / f"{aug_name}.txt"
                cv2.imwrite(str(aug_img_path), aug_img, [cv2.IMWRITE_JPEG_QUALITY, 90])
                write_yolo_label(aug_lbl_path, aug_labels)
                total_images += 1

    # Write data.yaml (manual to avoid pyyaml dependency)
    yaml_path = output_dir / "data.yaml"
    names_str = "\n".join(f"  - {name}" for name in COMPONENT_CLASSES)
    yaml_path.write_text(
        f"path: {output_dir.resolve()}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(COMPONENT_CLASSES)}\n"
        f"names:\n{names_str}\n"
    )

    (output_dir / "classes.json").write_text(json.dumps(COMPONENT_CLASSES, indent=2))

    # Print stats
    class_counts = {i: 0 for i in range(len(COMPONENT_CLASSES))}
    for split in ("train", "val"):
        for lbl in (output_dir / "labels" / split).glob("*.txt"):
            for line in lbl.read_text().strip().splitlines():
                if line.strip():
                    cls_id = int(line.split()[0])
                    class_counts[cls_id] = class_counts.get(cls_id, 0) + 1

    print(f"\n{'─' * 55}")
    print(f"Total: {total_images} images ({total_images - len(LABELS)} augmented)")
    print(f"\nClass distribution (across all labels):")
    for i, name in enumerate(COMPONENT_CLASSES):
        c = class_counts.get(i, 0)
        if c > 0:
            bar = "#" * min(c // 2, 40)
            print(f"  {i:>2}. {name:<22} {c:>4}  {bar}")

    covered = sum(1 for c in class_counts.values() if c > 0)
    print(f"\n{covered}/{len(COMPONENT_CLASSES)} classes have at least one sample.")

    empty = [COMPONENT_CLASSES[i] for i, c in class_counts.items() if c == 0]
    if empty:
        print(f"Missing classes (need more data): {', '.join(empty)}")

    print(f"\nDataset ready at: {output_dir}")
    print(f"Next: python scripts/prepare_training_data.py --roboflow --local {output_dir}")
    print(f"      (to merge with Roboflow data and add more sources)")


if __name__ == "__main__":
    main()
