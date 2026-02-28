"""
YOLOv8 component-level training pipeline for CAT equipment inspection.

Trains on a pre-uploaded dataset from the Modal volume (uploaded via
scripts/upload_dataset.py) or downloads from Roboflow as fallback.

Setup:
    1. Prepare data:    python scripts/prepare_training_data.py --roboflow
    2. Upload data:     python scripts/upload_dataset.py
    3. Train:           modal run backend/modal_app/train_yolo.py
    4. Download weights: python scripts/get_trained_model.py
    5. Redeploy:        modal deploy modal_deploy.py

Options:
    modal run backend/modal_app/train_yolo.py --epochs 150 --model-size s --imgsz 640
    modal run backend/modal_app/train_yolo.py --model-size m --imgsz 640 --batch 32
"""

import modal

training_app = modal.App("dronecat-training")

models_volume = modal.Volume.from_name("dronecat-models", create_if_missing=True)

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
        "albumentations",
    )
)


def _load_volume_dataset(models_path):
    """Copy the pre-uploaded dataset from the Modal volume to /tmp for training."""
    import shutil
    from pathlib import Path

    src = Path(models_path) / "dataset"
    dst = Path("/tmp/training/dataset")

    if not src.exists():
        return None

    yaml_file = src / "data.yaml"
    if not yaml_file.exists():
        return None

    print("[DATA] Found pre-uploaded dataset on volume. Copying to /tmp...")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(str(src), str(dst))

    import yaml
    with open(dst / "data.yaml") as f:
        meta = yaml.safe_load(f)
    meta["path"] = str(dst)
    with open(dst / "data.yaml", "w") as f:
        yaml.dump(meta, f)

    n_train = len(list((dst / "images" / "train").glob("*"))) if (dst / "images" / "train").exists() else 0
    n_val = len(list((dst / "images" / "val").glob("*"))) if (dst / "images" / "val").exists() else 0
    print(f"[DATA] Volume dataset: {n_train} train, {n_val} val images")
    return dst / "data.yaml"


def _download_roboflow_fallback(rf_key):
    """Fallback: download from Roboflow if no volume dataset exists."""
    import shutil
    import yaml
    from pathlib import Path
    from roboflow import Roboflow

    work_dir = Path("/tmp/training")
    dataset_dir = work_dir / "dataset"
    for split in ("train", "val"):
        (dataset_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    print("[DATA] No volume dataset found. Downloading from Roboflow...")
    rf = Roboflow(api_key=rf_key)
    proj = rf.workspace("mohamed-sabek-6zmr6").project("excavators-cwlh0")
    dl = proj.version(4).download("yolov8", location=str(work_dir / "rf100"))
    rf_dir = Path(dl.location)

    with open(rf_dir / "data.yaml") as f:
        rf_yaml = yaml.safe_load(f)
    rf_classes = rf_yaml.get("names", [])
    if isinstance(rf_classes, dict):
        rf_classes = [rf_classes[k] for k in sorted(rf_classes.keys())]

    CLASS_REMAP = {
        "excavators": "excavator", "excavator": "excavator",
        "dump truck": None, "wheel loader": None,
        "truck": None, "crane": None, "dozer": None,
    }

    remap = {}
    for i, name in enumerate(rf_classes):
        unified = CLASS_REMAP.get(name.lower().strip())
        if unified and unified in COMPONENT_CLASSES:
            remap[i] = COMPONENT_CLASSES.index(unified)

    count = 0
    for src_split, dst_split in [("train", "train"), ("valid", "val"), ("test", "val")]:
        img_src = rf_dir / src_split / "images"
        lbl_src = rf_dir / src_split / "labels"
        if not img_src.exists():
            continue
        for img in img_src.iterdir():
            lbl = lbl_src / img.with_suffix(".txt").name
            if not lbl.exists():
                continue
            lines = []
            for line in lbl.read_text().strip().splitlines():
                if not line:
                    continue
                parts = line.split()
                dst_cls = remap.get(int(parts[0]))
                if dst_cls is not None:
                    lines.append(f"{dst_cls} {' '.join(parts[1:])}")
            if lines:
                shutil.copy(img, dataset_dir / "images" / dst_split / img.name)
                (dataset_dir / "labels" / dst_split / img.with_suffix(".txt").name).write_text("\n".join(lines) + "\n")
                count += 1

    print(f"[DATA] Roboflow fallback: {count} images (excavator class only)")

    yaml_path = dataset_dir / "data.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({
            "path": str(dataset_dir),
            "train": "images/train",
            "val": "images/val",
            "nc": len(COMPONENT_CLASSES),
            "names": COMPONENT_CLASSES,
        }, f)

    return yaml_path


@training_app.function(
    gpu="H100",
    image=_train_image,
    volumes={"/models": models_volume},
    timeout=14400,
    secrets=[],
)
def train(
    epochs: int = 150,
    model_size: str = "s",
    imgsz: int = 640,
    batch: int = 48,
    freeze_epochs: int = 10,
    patience: int = 30,
):
    import json
    import os
    import shutil
    from pathlib import Path
    from ultralytics import YOLO

    # ── Load dataset (volume first, Roboflow fallback) ────────────────────
    yaml_path = _load_volume_dataset("/models")
    if yaml_path is None:
        rf_key = os.environ.get("ROBOFLOW_API_KEY", "")
        if not rf_key:
            raise RuntimeError(
                "No dataset on volume and no ROBOFLOW_API_KEY.\n"
                "Either upload a dataset: python scripts/upload_dataset.py\n"
                "Or set: modal secret create roboflow-api-key ROBOFLOW_API_KEY=<key>"
            )
        yaml_path = _download_roboflow_fallback(rf_key)

    # ── Phase 1: Frozen backbone (transfer learning) ──────────────────────
    model_name = f"yolov8{model_size}.pt"
    print(f"\n[TRAIN] Phase 1: Frozen backbone — {model_name}, {freeze_epochs} epochs, imgsz={imgsz}")
    model = YOLO(model_name)

    if freeze_epochs > 0:
        model.train(
            data=str(yaml_path),
            epochs=freeze_epochs,
            imgsz=imgsz,
            batch=batch,
            freeze=10,
            project="/tmp/runs",
            name="dronecat_frozen",
            patience=freeze_epochs,
            cache=True,
            save=True,
            verbose=True,
            lr0=0.01,
            lrf=0.1,
            warmup_epochs=3,
            mosaic=1.0,
            mixup=0.1,
            copy_paste=0.1,
            degrees=15.0,
            scale=0.5,
            fliplr=0.5,
            hsv_h=0.015,
            hsv_s=0.5,
            hsv_v=0.3,
        )
        frozen_best = Path("/tmp/runs/dronecat_frozen/weights/best.pt")
        if frozen_best.exists():
            model = YOLO(str(frozen_best))
            print("[TRAIN] Phase 1 complete. Loading best frozen checkpoint.")
        else:
            print("[TRAIN] Phase 1 produced no checkpoint — continuing with base model.")

    # ── Phase 2: Full fine-tune ───────────────────────────────────────────
    remaining = epochs - freeze_epochs
    print(f"\n[TRAIN] Phase 2: Full fine-tune — {remaining} epochs")
    results = model.train(
        data=str(yaml_path),
        epochs=remaining,
        imgsz=imgsz,
        batch=batch,
        project="/tmp/runs",
        name="dronecat_components",
        patience=patience,
        cache=True,
        save=True,
        verbose=True,
        lr0=0.001,
        lrf=0.01,
        warmup_epochs=3,
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.15,
        degrees=10.0,
        scale=0.5,
        translate=0.2,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        cls=0.5,
        box=7.5,
        dfl=1.5,
    )

    # ── Save weights to volume ────────────────────────────────────────────
    models_path = Path("/models")
    best = Path("/tmp/runs/dronecat_components/weights/best.pt")
    last = Path("/tmp/runs/dronecat_components/weights/last.pt")

    if best.exists():
        shutil.copy(best, models_path / "dronecat_yolo_best.pt")
        print("[SAVE] dronecat_yolo_best.pt → volume")
    if last.exists():
        shutil.copy(last, models_path / "dronecat_yolo_last.pt")
        print("[SAVE] dronecat_yolo_last.pt → volume")

    (models_path / "classes.json").write_text(json.dumps(COMPONENT_CLASSES))
    print("[SAVE] classes.json → volume")
    models_volume.commit()

    map50 = results.results_dict.get("metrics/mAP50(B)", 0)
    map50_95 = results.results_dict.get("metrics/mAP50-95(B)", 0)
    print(f"\n[DONE] mAP50={map50:.3f}  mAP50-95={map50_95:.3f}")
    print(f"[DONE] Classes: {COMPONENT_CLASSES}")
    print("[NEXT] python scripts/get_trained_model.py && modal deploy modal_deploy.py")

    return {
        "map50": map50,
        "map50_95": map50_95,
        "classes": COMPONENT_CLASSES,
        "epochs": epochs,
        "model_size": model_size,
    }


@training_app.local_entrypoint()
def main(
    epochs: int = 150,
    model_size: str = "s",
    imgsz: int = 640,
    batch: int = 48,
    freeze_epochs: int = 10,
):
    result = train.remote(
        epochs=epochs,
        model_size=model_size,
        imgsz=imgsz,
        batch=batch,
        freeze_epochs=freeze_epochs,
    )
    print(f"\nResult: {result}")
