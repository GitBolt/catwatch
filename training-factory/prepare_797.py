#!/usr/bin/env python3
"""
Convert augmented CAT 797 images into a YOLO detection dataset.

Classes derived dynamically from augmented dir structure:
  healthy/<Category>/  →  <category_normalized>_healthy
  damaged/<Category>/  →  <category_normalized>_damaged

Labels: whole-image bbox  <class_id> 0.5 0.5 1.0 1.0

Usage:
    python training-factory/prepare_797.py \
        --input  ~/Desktop/cat-scrape/augmented \
        --output data/797_dataset \
        --val-split 0.2
"""
import argparse
import json
import random
import re
import shutil
from pathlib import Path

import yaml


def normalize_category(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[&,]+", " ", s)
    s = re.sub(r"\s+", "_", s.strip())
    return re.sub(r"_+", "_", s)


def _collect_classes(aug_dir: Path) -> list:
    classes = set()
    for track in ("healthy", "damaged"):
        track_dir = aug_dir / track
        if not track_dir.exists():
            continue
        for cat_dir in track_dir.iterdir():
            if cat_dir.is_dir() and any(cat_dir.glob("*.jpg")):
                classes.add(f"{normalize_category(cat_dir.name)}_{track}")
    return sorted(classes)


def prepare_dataset(aug_dir: Path, out_dir: Path, val_split: float = 0.2):
    classes = _collect_classes(aug_dir)
    class_to_id = {c: i for i, c in enumerate(classes)}

    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    by_class = {c: [] for c in classes}
    for track in ("healthy", "damaged"):
        track_dir = aug_dir / track
        if not track_dir.exists():
            continue
        for cat_dir in sorted(track_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            cls = f"{normalize_category(cat_dir.name)}_{track}"
            if cls in by_class:
                by_class[cls].extend(sorted(cat_dir.glob("*.jpg")))

    random.seed(42)
    total_train = total_val = 0

    for cls, imgs in by_class.items():
        random.shuffle(imgs)
        n_val = max(1, int(len(imgs) * val_split)) if val_split > 0 and len(imgs) > 1 else 0
        label_line = f"{class_to_id[cls]} 0.5 0.5 1.0 1.0\n"
        for split_name, split_imgs in [("val", imgs[:n_val]), ("train", imgs[n_val:])]:
            for img in split_imgs:
                shutil.copy(img, out_dir / "images" / split_name / img.name)
                (out_dir / "labels" / split_name / img.with_suffix(".txt").name).write_text(label_line)
                if split_name == "train":
                    total_train += 1
                else:
                    total_val += 1

    (out_dir / "data.yaml").write_text(yaml.dump({
        "path":  str(out_dir.resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    len(classes),
        "names": classes,
    }, default_flow_style=False))
    (out_dir / "classes.json").write_text(json.dumps(classes, indent=2))

    print(f"[prepare] {len(classes)} classes, {total_train} train, {total_val} val → {out_dir}")
    return out_dir / "data.yaml"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",     required=True, type=Path)
    parser.add_argument("--output",    required=True, type=Path)
    parser.add_argument("--val-split", type=float, default=0.2)
    args = parser.parse_args()
    prepare_dataset(args.input, args.output, args.val_split)


if __name__ == "__main__":
    main()
