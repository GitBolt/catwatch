#!/usr/bin/env python3
"""
Prepare a component-level YOLO training dataset for CAT equipment inspection.

Data sources (all optional, at least one required):
  1. Roboflow Universe downloads  (--roboflow)
  2. Local YOLO-format dataset     (--local /path/to/dataset)
  3. Frame extraction from video   (--video /path/to/walkaround.mp4)

Usage:
    # Download from Roboflow + merge any local labeled data
    export ROBOFLOW_API_KEY=<your_key>
    python scripts/prepare_training_data.py --roboflow --local data/custom_labels

    # Extract frames from walkaround video (label these in Roboflow/CVAT afterwards)
    python scripts/prepare_training_data.py --video recordings/walkaround.mp4 --fps 2

    # Just validate and report on an existing dataset
    python scripts/prepare_training_data.py --local data/component_dataset --stats-only
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

COMPONENT_CLASSES = [
    "track_roller",
    "track_shoe",
    "sprocket",
    "idler",
    "track_chain",
    "final_drive",
    "hydraulic_hose",
    "hydraulic_cylinder",
    "bucket",
    "bucket_teeth",
    "cutting_edge",
    "boom",
    "stick",
    "cab",
    "cab_glass",
    "step",
    "handrail",
    "radiator",
    "engine_compartment",
    "exhaust",
    "tire",
    "rim",
    "coupler",
    "excavator",
]

# Maps source dataset class names (lowercased) → our unified class names.
# Add entries here as you discover new dataset label conventions.
CLASS_REMAP = {
    # Direct matches
    "track_roller": "track_roller", "track roller": "track_roller", "roller": "track_roller",
    "track_shoe": "track_shoe", "track shoe": "track_shoe", "shoe": "track_shoe",
    "sprocket": "sprocket",
    "idler": "idler",
    "track_chain": "track_chain", "track chain": "track_chain", "track": "track_chain",
    "final_drive": "final_drive", "final drive": "final_drive",
    "hydraulic_hose": "hydraulic_hose", "hydraulic hose": "hydraulic_hose",
    "hose": "hydraulic_hose", "hoses": "hydraulic_hose",
    "hydraulic_cylinder": "hydraulic_cylinder", "hydraulic cylinder": "hydraulic_cylinder",
    "cylinder": "hydraulic_cylinder",
    "bucket": "bucket",
    "bucket_teeth": "bucket_teeth", "bucket teeth": "bucket_teeth",
    "teeth": "bucket_teeth", "tooth": "bucket_teeth",
    "cutting_edge": "cutting_edge", "cutting edge": "cutting_edge",
    "boom": "boom", "boom arm": "boom", "boom_arm": "boom",
    "stick": "stick", "arm": "stick",
    "cab": "cab", "cabin": "cab",
    "cab_glass": "cab_glass", "cab glass": "cab_glass",
    "windshield": "cab_glass", "glass": "cab_glass",
    "step": "step", "steps": "step",
    "handrail": "handrail", "handrails": "handrail", "railing": "handrail",
    "ladder": "handrail",
    "radiator": "radiator",
    "engine_compartment": "engine_compartment", "engine compartment": "engine_compartment",
    "engine": "engine_compartment",
    "exhaust": "exhaust", "exhaust stack": "exhaust",
    "tire": "tire", "tyre": "tire",
    "rim": "rim", "wheel": "rim",
    "coupler": "coupler", "quick coupler": "coupler",
    "excavator": "excavator", "excavators": "excavator",
    "dump_truck": None, "dump truck": None,
    "loader": None, "wheel loader": None,
    "crane": None, "dozer": None,
}

# Roboflow dataset sources — (workspace, project, version) tuples.
# Add new datasets here as you find them on universe.roboflow.com.
ROBOFLOW_SOURCES = [
    {
        "name": "rf100_excavators",
        "workspace": "mohamed-sabek-6zmr6",
        "project": "excavators-cwlh0",
        "version": 4,
    },
    # Add more datasets here, e.g.:
    # {
    #     "name": "heavy_equipment_parts",
    #     "workspace": "some-workspace",
    #     "project": "excavator-parts-xyz",
    #     "version": 1,
    # },
]


def build_remap(src_classes):
    """Build a {src_idx: dst_idx} mapping from source class list to our unified classes."""
    remap = {}
    for i, name in enumerate(src_classes):
        key = name.lower().strip()
        unified = CLASS_REMAP.get(key)
        if unified and unified in COMPONENT_CLASSES:
            remap[i] = COMPONENT_CLASSES.index(unified)
    return remap


def remap_label_file(src_path, dst_path, remap):
    """Remap class IDs in a YOLO label file. Returns True if any valid labels written."""
    lines = []
    for line in src_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        parts = line.split()
        dst_cls = remap.get(int(parts[0]))
        if dst_cls is not None:
            lines.append(f"{dst_cls} {' '.join(parts[1:])}")
    if lines:
        dst_path.write_text("\n".join(lines) + "\n")
        return True
    return False


def copy_split(src_img_dir, src_lbl_dir, dst_img_dir, dst_lbl_dir, remap, prefix=""):
    """Copy and remap one split of a dataset. Returns count of images copied."""
    if not src_img_dir.exists():
        return 0
    count = 0
    for img in sorted(src_img_dir.iterdir()):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            continue
        lbl = src_lbl_dir / img.with_suffix(".txt").name
        if not lbl.exists():
            continue
        dst_name = f"{prefix}{img.name}" if prefix else img.name
        dst_lbl = dst_lbl_dir / Path(dst_name).with_suffix(".txt").name
        if remap_label_file(lbl, dst_lbl, remap):
            shutil.copy(img, dst_img_dir / dst_name)
            count += 1
    return count


def download_roboflow_sources(work_dir):
    """Download all configured Roboflow datasets. Returns list of (name, dir, classes) tuples."""
    api_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not api_key:
        print("  ROBOFLOW_API_KEY not set — skipping Roboflow downloads.")
        print("  Get a free key at https://app.roboflow.com")
        return []

    try:
        from roboflow import Roboflow
        import yaml
    except ImportError:
        print("  pip install roboflow pyyaml — required for Roboflow downloads.")
        return []

    downloaded = []
    for src in ROBOFLOW_SOURCES:
        print(f"  Downloading {src['name']}...")
        try:
            rf = Roboflow(api_key=api_key)
            proj = rf.workspace(src["workspace"]).project(src["project"])
            dl = proj.version(src["version"]).download("yolov8", location=str(work_dir / src["name"]))
            rf_dir = Path(dl.location)
            with open(rf_dir / "data.yaml") as f:
                rf_yaml = yaml.safe_load(f)
            classes = rf_yaml.get("names", [])
            if isinstance(classes, dict):
                classes = [classes[k] for k in sorted(classes.keys())]
            print(f"    Classes: {classes}")
            downloaded.append((src["name"], rf_dir, classes))
        except Exception as e:
            print(f"    Failed: {e}")
    return downloaded


def ingest_local_dataset(local_dir):
    """Detect the structure of a local YOLO dataset and return split paths + classes."""
    local_dir = Path(local_dir)
    if not local_dir.exists():
        print(f"  Local dataset not found: {local_dir}")
        return None

    import yaml

    yaml_path = local_dir / "data.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            meta = yaml.safe_load(f)
        classes = meta.get("names", [])
        if isinstance(classes, dict):
            classes = [classes[k] for k in sorted(classes.keys())]
        print(f"  Found data.yaml with classes: {classes}")
        return ("local", local_dir, classes)

    # No data.yaml — assume flat structure: images/ and labels/ with train/val splits
    if (local_dir / "images").exists() and (local_dir / "labels").exists():
        print(f"  Found images/ and labels/ directories (no data.yaml)")
        # Assume class indices are already our unified classes
        return ("local", local_dir, COMPONENT_CLASSES)

    print(f"  Could not detect dataset structure in {local_dir}")
    print(f"  Expected either data.yaml or images/ + labels/ directories")
    return None


def extract_video_frames(video_path, output_dir, fps=2):
    """Extract frames from a video at the given FPS for labeling."""
    try:
        import cv2
    except ImportError:
        print("  pip install opencv-python — required for video extraction.")
        return 0

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"  Cannot open video: {video_path}")
        return 0

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = max(1, int(video_fps / fps))
    stem = video_path.stem

    count = 0
    frame_num = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_num % frame_interval == 0:
            out_path = output_dir / f"{stem}_{count:05d}.jpg"
            cv2.imwrite(str(out_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            count += 1
        frame_num += 1
    cap.release()
    return count


def print_dataset_stats(dataset_dir):
    """Print class distribution and split sizes for the final dataset."""
    dataset_dir = Path(dataset_dir)
    print("\n── Dataset Statistics ─────────────────────────────────")

    total = 0
    class_counts = {i: 0 for i in range(len(COMPONENT_CLASSES))}

    for split in ("train", "val"):
        lbl_dir = dataset_dir / "labels" / split
        img_dir = dataset_dir / "images" / split
        if not lbl_dir.exists():
            continue
        n_images = len(list(img_dir.glob("*"))) if img_dir.exists() else 0
        n_labels = 0
        for lbl in lbl_dir.glob("*.txt"):
            n_labels += 1
            for line in lbl.read_text().strip().splitlines():
                if line.strip():
                    cls_id = int(line.split()[0])
                    class_counts[cls_id] = class_counts.get(cls_id, 0) + 1
        print(f"  {split:>5}: {n_images} images, {n_labels} label files")
        total += n_images

    print(f"  Total: {total} images")
    print("\n  Class distribution:")
    for i, name in enumerate(COMPONENT_CLASSES):
        c = class_counts.get(i, 0)
        bar = "#" * min(c // 5, 40)
        if c > 0:
            print(f"    {i:>2}. {name:<22} {c:>5}  {bar}")

    empty_classes = [name for i, name in enumerate(COMPONENT_CLASSES) if class_counts.get(i, 0) == 0]
    if empty_classes:
        print(f"\n  WARNING: {len(empty_classes)} classes have ZERO samples:")
        for name in empty_classes:
            print(f"    - {name}")
        print("  You should add labeled data for these classes before training.")

    print("──────────────────────────────────────────────────────")


def main():
    parser = argparse.ArgumentParser(description="Prepare component-level YOLO training data")
    parser.add_argument("--roboflow", action="store_true", help="Download datasets from Roboflow Universe")
    parser.add_argument("--local", type=str, help="Path to a local YOLO-format dataset to merge in")
    parser.add_argument("--video", type=str, help="Extract frames from a walkaround video for labeling")
    parser.add_argument("--fps", type=float, default=2.0, help="Frames per second for video extraction (default: 2)")
    parser.add_argument("--output", type=str, default=str(DATA_DIR / "component_dataset"),
                        help="Output dataset directory")
    parser.add_argument("--val-split", type=float, default=0.15, help="Validation split ratio (default: 0.15)")
    parser.add_argument("--stats-only", action="store_true", help="Only print stats for existing dataset")
    args = parser.parse_args()

    output_dir = Path(args.output)

    if args.stats_only:
        if output_dir.exists():
            print_dataset_stats(output_dir)
        else:
            print(f"Dataset not found: {output_dir}")
        return

    if args.video:
        frames_dir = output_dir / "unlabeled_frames"
        print(f"\n[VIDEO] Extracting frames from {args.video} at {args.fps} fps...")
        n = extract_video_frames(args.video, frames_dir, fps=args.fps)
        print(f"[VIDEO] Extracted {n} frames → {frames_dir}")
        print(f"\nNext steps:")
        print(f"  1. Upload {frames_dir} to Roboflow (app.roboflow.com) or CVAT (cvat.ai)")
        print(f"  2. Draw bounding boxes using these class names:")
        for i, name in enumerate(COMPONENT_CLASSES):
            print(f"       {name}")
        print(f"  3. Export as 'YOLOv8' format")
        print(f"  4. Re-run: python {__file__} --local /path/to/exported_dataset")
        return

    if not args.roboflow and not args.local:
        parser.print_help()
        print("\nError: specify at least one data source (--roboflow, --local, or --video)")
        print("\nTip: run  python scripts/seed_from_catrack.py  first to create seed data")
        print("     from data/catrack_samples/, then re-run with --local data/component_dataset")
        sys.exit(1)

    # ── Build merged dataset ──────────────────────────────────────────────
    print(f"\n[PREP] Building component dataset → {output_dir}")

    for split in ("train", "val"):
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    work_dir = Path("/tmp/catwatch_data_prep")
    work_dir.mkdir(parents=True, exist_ok=True)

    sources = []

    if args.roboflow:
        print("\n[ROBOFLOW] Downloading datasets...")
        sources.extend(download_roboflow_sources(work_dir))

    if args.local:
        print(f"\n[LOCAL] Ingesting {args.local}...")
        result = ingest_local_dataset(args.local)
        if result:
            sources.append(result)

    if not sources:
        print("\nNo data sources produced usable datasets. Exiting.")
        sys.exit(1)

    # ── Merge all sources ─────────────────────────────────────────────────
    print(f"\n[MERGE] Merging {len(sources)} source(s)...")

    for name, src_dir, src_classes in sources:
        remap = build_remap(src_classes)
        mapped_classes = {COMPONENT_CLASSES[v] for v in remap.values()}
        print(f"  {name}: {len(src_classes)} source classes → {len(mapped_classes)} mapped ({', '.join(sorted(mapped_classes))})")

        prefix = f"{name}_"

        # Try standard YOLO splits
        for src_split, dst_split in [("train", "train"), ("valid", "val"), ("val", "val"), ("test", "val")]:
            img_dir = src_dir / src_split / "images"
            lbl_dir = src_dir / src_split / "labels"
            if not img_dir.exists():
                img_dir = src_dir / "images" / src_split
                lbl_dir = src_dir / "labels" / src_split
            if img_dir.exists():
                n = copy_split(
                    img_dir, lbl_dir,
                    output_dir / "images" / dst_split,
                    output_dir / "labels" / dst_split,
                    remap, prefix=prefix,
                )
                if n > 0:
                    print(f"    {src_split} → {dst_split}: {n} images")

    # ── Auto-split if val is empty ────────────────────────────────────────
    val_images = list((output_dir / "images" / "val").glob("*"))
    train_images = sorted((output_dir / "images" / "train").glob("*"))

    if not val_images and train_images:
        import random
        random.seed(42)
        random.shuffle(train_images)
        n_val = max(1, int(len(train_images) * args.val_split))
        print(f"\n[SPLIT] No validation data — auto-splitting {n_val} images from train")
        for img in train_images[:n_val]:
            lbl = output_dir / "labels" / "train" / img.with_suffix(".txt").name
            shutil.move(str(img), output_dir / "images" / "val" / img.name)
            if lbl.exists():
                shutil.move(str(lbl), output_dir / "labels" / "val" / lbl.name)

    # ── Write data.yaml ───────────────────────────────────────────────────
    import yaml
    yaml_path = output_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({
            "path": str(output_dir.resolve()),
            "train": "images/train",
            "val": "images/val",
            "nc": len(COMPONENT_CLASSES),
            "names": COMPONENT_CLASSES,
        }, f, default_flow_style=False)
    print(f"\n[YAML] Written: {yaml_path}")

    # ── Write classes.json for reference ──────────────────────────────────
    classes_path = output_dir / "classes.json"
    classes_path.write_text(json.dumps(COMPONENT_CLASSES, indent=2))

    print_dataset_stats(output_dir)

    print(f"\nDataset ready at: {output_dir}")
    print(f"Next steps:")
    print(f"  1. Review class distribution above — add more data for low-count classes")
    print(f"  2. Upload to Modal:  python scripts/upload_dataset.py")
    print(f"  3. Train:            modal run backend/modal_app/train_yolo.py")


if __name__ == "__main__":
    main()
