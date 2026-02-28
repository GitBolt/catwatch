"""
YOLOv10 training pipeline for Dronecat construction equipment detector.

Downloads the RF100 Excavators dataset (Excavator, Dump Truck, Wheel Loader)
from Roboflow, trains YOLOv10n on Modal A100, and saves weights to the
shared 'dronecat-models' volume where YoloDetector will pick them up automatically.

Setup:
    1. Get a free Roboflow API key at https://app.roboflow.com
    2. Create a Modal secret:
           modal secret create roboflow-api-key ROBOFLOW_API_KEY=<your_key>
    3. Run training:
           modal run backend/modal_app/train_yolo.py
    4. After training, download weights:
           python scripts/get_trained_model.py
    5. Redeploy:
           modal deploy modal_deploy.py
"""

import modal

# Separate app so training never touches the live inference deployment.
training_app = modal.App("dronecat-training")

# Same volume name as in __init__.py — Modal resolves by name, no import needed.
models_volume = modal.Volume.from_name("dronecat-models", create_if_missing=True)

# Unified class list written into data.yaml and classes.json in the volume.
UNIFIED_CLASSES = ["excavator", "dump_truck", "loader", "crane", "dozer"]

# Maps source dataset class names → unified names (None = discard).
# Keys are lowercased — lookup normalizes before matching.
_CLASS_MAP = {
    # RF100 excavators dataset
    "excavators": "excavator",
    "excavator": "excavator",
    "dump truck": "dump_truck",
    "wheel loader": "loader",
    # Pictor-v2 (add later)
    "truck": "dump_truck",
    "crane": "crane",
    "dozer": "dozer",
    "other": None,
}

_train_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "ultralytics>=8.3.0",
        "roboflow",
        "torch",
        "torchvision",
        "numpy",
        "Pillow",
        "pyyaml",
        "opencv-python-headless",
    )
)


@training_app.function(
    gpu="A100",
    image=_train_image,
    volumes={"/models": models_volume},
    timeout=7200,
    secrets=[modal.Secret.from_name("roboflow-api-key")],
)
def train(epochs: int = 100, model_size: str = "n", imgsz: int = 640, batch: int = 64):
    import json
    import os
    import shutil
    import yaml
    from pathlib import Path
    from ultralytics import YOLO

    rf_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not rf_key:
        raise RuntimeError(
            "ROBOFLOW_API_KEY not found. Create a Modal secret:\n"
            "  modal secret create roboflow-api-key ROBOFLOW_API_KEY=<your_key>"
        )

    work_dir = Path("/tmp/training")
    dataset_dir = work_dir / "dataset"
    for split in ("train", "val", "test"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    # ── Download RF100 excavators ────────────────────────────────────────────
    print("[DATA] Downloading RF100 excavators from Roboflow...")
    from roboflow import Roboflow
    rf = Roboflow(api_key=rf_key)
    proj = rf.workspace("mohamed-sabek-6zmr6").project("excavators-cwlh0")
    dl = proj.version(4).download("yolov8", location=str(work_dir / "rf100"))
    rf_dir = Path(dl.location)

    with open(rf_dir / "data.yaml") as f:
        rf_yaml = yaml.safe_load(f)
    rf_classes = rf_yaml.get("names", [])
    print(f"[DATA] RF100 classes: {rf_classes}")

    # ── Class remapping helpers ───────────────────────────────────────────────
    def build_remap(src_classes):
        remap = {}
        for i, name in enumerate(src_classes):
            unified = _CLASS_MAP.get(name.lower().strip())
            remap[i] = UNIFIED_CLASSES.index(unified) if unified in UNIFIED_CLASSES else None
        return remap

    def remap_label_file(src_path, dst_path, remap):
        lines = []
        for line in src_path.read_text().strip().splitlines():
            if not line:
                continue
            parts = line.split()
            dst_cls = remap.get(int(parts[0]))
            if dst_cls is not None:
                lines.append(f"{dst_cls} {' '.join(parts[1:])}")
        if lines:
            dst_path.write_text("\n".join(lines) + "\n")

    def copy_split(src_root, src_split, dst_split, remap):
        img_src = src_root / src_split / "images"
        lbl_src = src_root / src_split / "labels"
        if not img_src.exists():
            return 0
        count = 0
        for img in img_src.iterdir():
            lbl = lbl_src / img.with_suffix(".txt").name
            if not lbl.exists():
                continue
            has_valid = any(
                remap.get(int(ln.split()[0])) is not None
                for ln in lbl.read_text().strip().splitlines() if ln
            )
            if has_valid:
                shutil.copy(img, dataset_dir / "images" / dst_split / img.name)
                remap_label_file(lbl, dataset_dir / "labels" / dst_split / lbl.name, remap)
                count += 1
        return count

    rf_remap = build_remap(rf_classes)
    n_train = copy_split(rf_dir, "train", "train", rf_remap)
    n_val   = copy_split(rf_dir, "valid", "val",   rf_remap)
    n_test  = copy_split(rf_dir, "test",  "test",  rf_remap)
    print(f"[DATA] RF100 → train:{n_train}  val:{n_val}  test:{n_test}")

    if n_train == 0:
        raise RuntimeError("No training images after remapping. Check RF100 dataset version/classes.")

    # ── Write data.yaml ───────────────────────────────────────────────────────
    yaml_path = dataset_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({
            "path": str(dataset_dir),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(UNIFIED_CLASSES),
            "names": UNIFIED_CLASSES,
        }, f)
    print(f"[DATA] data.yaml written: {UNIFIED_CLASSES}")

    # ── Train ─────────────────────────────────────────────────────────────────
    print(f"[TRAIN] YOLOv10{model_size}  epochs={epochs}  imgsz={imgsz}  batch={batch}")
    model = YOLO(f"yolov10{model_size}.pt")
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project="/tmp/runs",
        name="dronecat_v1",
        patience=20,
        cache=True,
        save=True,
        verbose=True,
    )

    # ── Save weights to volume ────────────────────────────────────────────────
    models_path = Path("/models")
    best = Path("/tmp/runs/dronecat_v1/weights/best.pt")
    last = Path("/tmp/runs/dronecat_v1/weights/last.pt")

    if best.exists():
        shutil.copy(best, models_path / "dronecat_yolo_best.pt")
        print("[TRAIN] Saved dronecat_yolo_best.pt to volume.")
    if last.exists():
        shutil.copy(last, models_path / "dronecat_yolo_last.pt")

    (models_path / "classes.json").write_text(json.dumps(UNIFIED_CLASSES))
    models_volume.commit()

    map50 = results.results_dict.get("metrics/mAP50(B)", 0)
    print(f"[TRAIN] Done. mAP50={map50:.3f}")
    print("[TRAIN] Next: python scripts/get_trained_model.py  &&  modal deploy modal_deploy.py")
    return {"map50": map50, "classes": UNIFIED_CLASSES}


@training_app.local_entrypoint()
def main(epochs: int = 100, model_size: str = "n"):
    result = train.remote(epochs=epochs, model_size=model_size)
    print(f"\nResult: {result}")
