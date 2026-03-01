# CAT 797 YOLO Training Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a pipeline that augments CAT 797 part images (healthy + damage variants), prepares a YOLO dataset with `<category>_healthy` / `<category>_damaged` classes, and fine-tunes YOLO on Modal H100s.

**Architecture:** Two local scripts (`augment.py`, `prepare_797.py`) in `training-factory/` produce a YOLO-format dataset from cross-referenced originals and Nano Banana damage variants. The existing Modal training function is updated to read classes dynamically from `data.yaml` and support multi-GPU H100 runs.

**Tech Stack:** Python 3.11, albumentations, Pillow, PyYAML, ultralytics, Modal

---

## Cross-Reference Logic

```
cat_797_parts/images/<category>/<Part Name (SKU)>.jpg   ← originals (185 total)
cat-scrape/output/<category>/<Part Name (SKU)>/         ← damage dirs (done + *.png)
```

- **Matched** (101 parts): original exists + damage dir has `done` + ≥1 `.png`
  - Original → `<category>_healthy`
  - Each `.png` in damage dir → `<category>_damaged`
- **Unmatched** (83 parts): original only → `<category>_healthy`

Augmented output layout:
```
<output>/healthy/<category>/<stem>_aug<N>.jpg
<output>/damaged/<category>/<stem>_<damage_stem>_aug<N>.jpg
```

---

## Class List (derived from `cat_797_parts/images/` categories)

Normalized: lowercase, spaces→`_`, `&`→removed, `,`→removed.

Categories that will have `_damaged` variants (have at least some matched parts):
`cabs`, `drivetrain`, `electrical_electronics`, `engine`, `filters_fluids`,
`ground_engaging_tools`, `hardware_seals_consumables`, `structures_other_systems`, `undercarriage`

Categories with `_healthy` only (no damage variants found):
`hoses_tubes`, `hydraulics`, `upgrade_repair_kits`, `workshop_supplies`

Full class list built dynamically at prepare time from what's actually present in augmented output.

---

## Task 1: `training-factory/augment.py` — skeleton + cross-reference

**Files:**
- Create: `training-factory/augment.py`
- Create: `tests/training_factory/test_augment.py`

**Step 1: Write the failing test**

```python
# tests/training_factory/test_augment.py
from pathlib import Path
import pytest


def test_cross_reference_matched(tmp_path):
    """Parts with a done damage dir should be matched."""
    from training_factory.augment import cross_reference

    parts = tmp_path / "parts" / "Engine"
    parts.mkdir(parents=True)
    (parts / "Fuel Pump (123-4567).jpg").write_bytes(b"img")

    dmg = tmp_path / "damage" / "Engine" / "Fuel Pump (123-4567)"
    dmg.mkdir(parents=True)
    (dmg / "done").write_text("{}")
    (dmg / "fuel_pump_wear_1.png").write_bytes(b"img")

    matched, unmatched = cross_reference(tmp_path / "parts", tmp_path / "damage")
    assert len(matched) == 1
    assert matched[0][0].name == "Fuel Pump (123-4567).jpg"
    assert len(matched[0][1]) == 1
    assert len(unmatched) == 0


def test_cross_reference_unmatched(tmp_path):
    """Parts without a done damage dir should be unmatched."""
    from training_factory.augment import cross_reference

    parts = tmp_path / "parts" / "Hydraulics"
    parts.mkdir(parents=True)
    (parts / "Pump Assembly (888-0001).jpg").write_bytes(b"img")

    matched, unmatched = cross_reference(tmp_path / "parts", tmp_path / "damage")
    assert len(matched) == 0
    assert len(unmatched) == 1
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/evan/Desktop/dronecat
python -m pytest tests/training_factory/test_augment.py -v
```
Expected: `ModuleNotFoundError: No module named 'training_factory'`

**Step 3: Write the module skeleton**

```python
# training-factory/augment.py
#!/usr/bin/env python3
"""
Augment CAT 797 part images (healthy originals + Nano Banana damage variants).

Usage:
    python training-factory/augment.py \
        --parts ~/Desktop/cat_797_parts/images \
        --damage ~/Desktop/cat-scrape/output \
        --output ~/Desktop/cat-scrape/augmented \
        --variants 6
"""
import argparse
import sys
from pathlib import Path


def cross_reference(parts_dir: Path, damage_dir: Path):
    """
    Returns (matched, unmatched).
      matched   = [(orig_path, [damage_img_path, ...]), ...]
      unmatched = [orig_path, ...]
    """
    matched, unmatched = [], []
    for img in sorted(parts_dir.rglob("*.jpg")) + sorted(parts_dir.rglob("*.png")):
        cat = img.parent.name
        dmg_dir = damage_dir / cat / img.stem
        done = dmg_dir / "done"
        variants = sorted(dmg_dir.glob("*.png")) if dmg_dir.exists() else []
        if done.exists() and variants:
            matched.append((img, variants))
        else:
            unmatched.append(img)
    return matched, unmatched


if __name__ == "__main__":
    pass  # main() added in Task 2
```

Also create `training-factory/__init__.py` (empty) and `tests/training_factory/__init__.py` (empty) so pytest can import.

**Note:** `training-factory` has a hyphen. Add a `conftest.py` at repo root (or use `sys.path`) to make it importable as `training_factory`:

```python
# tests/training_factory/conftest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training-factory"))
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/training_factory/test_augment.py -v
```
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add training-factory/augment.py training-factory/__init__.py \
        tests/training_factory/
git commit -m "feat: add augment.py skeleton with cross_reference"
```

---

## Task 2: `augment.py` — albumentations pipeline + write augmented images

**Files:**
- Modify: `training-factory/augment.py`
- Modify: `tests/training_factory/test_augment.py`

**Step 1: Write the failing test**

```python
# append to tests/training_factory/test_augment.py
import numpy as np
from PIL import Image as PILImage


def _make_jpg(path: Path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = PILImage.fromarray(np.random.randint(0, 255, (*size, 3), dtype=np.uint8))
    img.save(path, format="JPEG")


def test_augment_matched_part_produces_variants(tmp_path):
    """Each matched part should produce N healthy + N*len(variants) damaged images."""
    from training_factory.augment import augment_dataset

    parts = tmp_path / "parts" / "Engine"
    orig = parts / "Fuel Pump (123-4567).jpg"
    _make_jpg(orig)

    dmg_dir = tmp_path / "damage" / "Engine" / "Fuel Pump (123-4567)"
    dmg_dir.mkdir(parents=True)
    (dmg_dir / "done").write_text("{}")
    dmg_img = dmg_dir / "fuel_pump_wear_1.png"
    _make_jpg(dmg_img)

    out = tmp_path / "augmented"
    augment_dataset(tmp_path / "parts", tmp_path / "damage", out, variants=3)

    healthy = list((out / "healthy" / "Engine").glob("*.jpg"))
    damaged = list((out / "damaged" / "Engine").glob("*.jpg"))
    assert len(healthy) == 3   # 3 augmented variants of original
    assert len(damaged) == 3   # 3 augmented variants of 1 damage image


def test_augment_unmatched_part_produces_healthy_only(tmp_path):
    from training_factory.augment import augment_dataset

    parts = tmp_path / "parts" / "Hydraulics"
    orig = parts / "Pump (000-0001).jpg"
    _make_jpg(orig)

    out = tmp_path / "augmented"
    augment_dataset(tmp_path / "parts", tmp_path / "damage", out, variants=2)

    healthy = list((out / "healthy" / "Hydraulics").glob("*.jpg"))
    damaged = list((out / "damaged").rglob("*.jpg")) if (out / "damaged").exists() else []
    assert len(healthy) == 2
    assert len(damaged) == 0
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/training_factory/test_augment.py::test_augment_matched_part_produces_variants -v
```
Expected: `AttributeError: module has no attribute 'augment_dataset'`

**Step 3: Implement augmentation pipeline**

```python
# Add to training-factory/augment.py (after cross_reference, before __main__)
import random
import numpy as np
from PIL import Image


def _build_pipeline():
    import albumentations as A
    return A.Compose([
        A.OneOf([
            A.RandomBrightnessContrast(brightness_limit=0.4, contrast_limit=0.4),
            A.RandomGamma(gamma_limit=(60, 140)),
            A.CLAHE(clip_limit=4.0),
        ], p=0.8),
        A.OneOf([
            A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=40, val_shift_limit=30),
            A.RGBShift(r_shift_limit=20, g_shift_limit=20, b_shift_limit=20),
        ], p=0.5),
        A.RandomShadow(num_shadows_lower=1, num_shadows_upper=2, p=0.2),
        A.OneOf([
            A.HorizontalFlip(),
            A.VerticalFlip(),
            A.RandomRotate90(),
        ], p=0.7),
        A.OneOf([
            A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.2,
                               rotate_limit=30, border_mode=0),
            A.Perspective(scale=(0.05, 0.1)),
        ], p=0.4),
    ])


def _augment_image(img_path: Path, out_dir: Path, stem: str, n: int, pipeline) -> list[Path]:
    """Write n augmented variants. Returns list of written paths."""
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for i in range(n):
        aug = pipeline(image=arr)["image"]
        out_path = out_dir / f"{stem}_aug{i}.jpg"
        Image.fromarray(aug).save(out_path, format="JPEG", quality=92)
        written.append(out_path)
    return written


def augment_dataset(parts_dir: Path, damage_dir: Path, out_dir: Path, variants: int = 6):
    """
    Augments all parts and writes to:
      out_dir/healthy/<category>/<stem>_augN.jpg
      out_dir/damaged/<category>/<stem>_<damage_stem>_augN.jpg
    """
    pipeline = _build_pipeline()
    matched, unmatched = cross_reference(parts_dir, damage_dir)

    total_healthy = total_damaged = 0

    for orig, dmg_imgs in matched:
        cat = orig.parent.name
        # healthy: augment original
        out = _augment_image(orig, out_dir / "healthy" / cat, orig.stem, variants, pipeline)
        total_healthy += len(out)
        # damaged: augment each damage variant
        for dmg in dmg_imgs:
            stem = f"{orig.stem}_{dmg.stem}"
            out = _augment_image(dmg, out_dir / "damaged" / cat, stem, variants, pipeline)
            total_damaged += len(out)

    for orig in unmatched:
        cat = orig.parent.name
        out = _augment_image(orig, out_dir / "healthy" / cat, orig.stem, variants, pipeline)
        total_healthy += len(out)

    print(f"[augment] {total_healthy} healthy, {total_damaged} damaged → {out_dir}")
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/training_factory/test_augment.py -v
```
Expected: PASS (all 4 tests)

**Step 5: Add CLI entrypoint**

```python
# Replace the `if __name__ == "__main__": pass` block
def main():
    parser = argparse.ArgumentParser(description="Augment CAT 797 part images")
    parser.add_argument("--parts",    required=True, type=Path)
    parser.add_argument("--damage",   required=True, type=Path)
    parser.add_argument("--output",   required=True, type=Path)
    parser.add_argument("--variants", type=int, default=6)
    args = parser.parse_args()
    augment_dataset(args.parts, args.damage, args.output, args.variants)


if __name__ == "__main__":
    main()
```

**Step 6: Commit**

```bash
git add training-factory/augment.py tests/training_factory/test_augment.py
git commit -m "feat: augment.py — lighting/orientation variants, no API calls"
```

---

## Task 3: `training-factory/prepare_797.py` — YOLO dataset builder

**Files:**
- Create: `training-factory/prepare_797.py`
- Create: `tests/training_factory/test_prepare_797.py`

**Step 1: Write the failing tests**

```python
# tests/training_factory/test_prepare_797.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training-factory"))

import numpy as np
from PIL import Image as PILImage
import yaml, pytest


def _write_img(path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.fromarray(
        np.random.randint(0, 255, (*size, 3), dtype=np.uint8)
    ).save(path, format="JPEG")


def test_normalize_category():
    from prepare_797 import normalize_category
    assert normalize_category("Electrical & Electronics") == "electrical_electronics"
    assert normalize_category("Filters & Fluids") == "filters_fluids"
    assert normalize_category("Hardware, Seals, & Consumables") == "hardware_seals_consumables"
    assert normalize_category("Hoses & Tubes") == "hoses_tubes"


def test_prepare_writes_labels_and_yaml(tmp_path):
    from prepare_797 import prepare_dataset

    aug = tmp_path / "augmented"
    for cat in ("Engine", "Hydraulics"):
        for track in ("healthy", "damaged"):
            d = aug / track / cat
            d.mkdir(parents=True)
            _write_img(d / f"part_{track}_aug0.jpg")

    out = tmp_path / "dataset"
    prepare_dataset(aug, out, val_split=0.0)  # no val for simplicity

    # data.yaml must exist
    yaml_path = out / "data.yaml"
    assert yaml_path.exists()
    meta = yaml.safe_load(yaml_path.read_text())
    assert meta["nc"] == len(meta["names"])
    assert "engine_healthy" in meta["names"]
    assert "engine_damaged" in meta["names"]
    assert "hydraulics_healthy" in meta["names"]

    # Every image should have a label
    imgs = list((out / "images" / "train").glob("*.jpg"))
    assert len(imgs) > 0
    for img in imgs:
        lbl = out / "labels" / "train" / img.with_suffix(".txt").name
        assert lbl.exists(), f"Missing label for {img.name}"
        lines = lbl.read_text().strip().splitlines()
        assert len(lines) == 1
        parts = lines[0].split()
        assert len(parts) == 5
        assert parts[1:] == ["0.5", "0.5", "1.0", "1.0"]


def test_val_split_is_respected(tmp_path):
    from prepare_797 import prepare_dataset

    aug = tmp_path / "augmented" / "healthy" / "Engine"
    aug.mkdir(parents=True)
    for i in range(10):
        _write_img(aug / f"part_aug{i}.jpg")

    out = tmp_path / "dataset"
    prepare_dataset(tmp_path / "augmented", out, val_split=0.2)

    train_imgs = list((out / "images" / "train").glob("*.jpg"))
    val_imgs   = list((out / "images" / "val").glob("*.jpg"))
    assert len(val_imgs) == 2
    assert len(train_imgs) == 8
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/training_factory/test_prepare_797.py -v
```
Expected: `ModuleNotFoundError: No module named 'prepare_797'`

**Step 3: Implement `prepare_797.py`**

```python
#!/usr/bin/env python3
"""
Convert augmented CAT 797 images to a YOLO detection dataset.

Classes are derived dynamically from what's present in the augmented dir:
  healthy/<Category>/  → <category_normalized>_healthy
  damaged/<Category>/  → <category_normalized>_damaged

Labels use whole-image bounding boxes: <class_id> 0.5 0.5 1.0 1.0

Usage:
    python training-factory/prepare_797.py \
        --input  ~/Desktop/cat-scrape/augmented \
        --output data/797_dataset \
        --val-split 0.2
"""
import argparse
import random
import re
import shutil
import yaml
from pathlib import Path


def normalize_category(name: str) -> str:
    """'Electrical & Electronics' → 'electrical_electronics'"""
    s = name.lower()
    s = re.sub(r"[&,]+", " ", s)
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"_+", "_", s)
    return s


def _collect_classes(aug_dir: Path) -> list[str]:
    """Scan augmented dir and return sorted list of class names present."""
    classes = set()
    for track in ("healthy", "damaged"):
        track_dir = aug_dir / track
        if not track_dir.exists():
            continue
        for cat_dir in track_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            if any(cat_dir.glob("*.jpg")):
                classes.add(f"{normalize_category(cat_dir.name)}_{track}")
    return sorted(classes)


def prepare_dataset(aug_dir: Path, out_dir: Path, val_split: float = 0.2):
    classes = _collect_classes(aug_dir)
    class_to_id = {c: i for i, c in enumerate(classes)}

    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Collect all (img_path, class_name) pairs grouped by class for stratified split
    by_class: dict[str, list[Path]] = {c: [] for c in classes}
    for track in ("healthy", "damaged"):
        track_dir = aug_dir / track
        if not track_dir.exists():
            continue
        for cat_dir in sorted(track_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            cls = f"{normalize_category(cat_dir.name)}_{track}"
            if cls not in by_class:
                continue
            by_class[cls].extend(sorted(cat_dir.glob("*.jpg")))

    random.seed(42)
    total_train = total_val = 0

    for cls, imgs in by_class.items():
        random.shuffle(imgs)
        n_val = max(1, int(len(imgs) * val_split)) if val_split > 0 and len(imgs) > 1 else 0
        splits = [("val", imgs[:n_val]), ("train", imgs[n_val:])]
        cls_id = class_to_id[cls]
        label_line = f"{cls_id} 0.5 0.5 1.0 1.0\n"

        for split_name, split_imgs in splits:
            for img in split_imgs:
                dst_img = out_dir / "images" / split_name / img.name
                dst_lbl = out_dir / "labels" / split_name / img.with_suffix(".txt").name
                shutil.copy(img, dst_img)
                dst_lbl.write_text(label_line)
                if split_name == "train":
                    total_train += 1
                else:
                    total_val += 1

    yaml_path = out_dir / "data.yaml"
    yaml_path.write_text(yaml.dump({
        "path":  str(out_dir.resolve()),
        "train": "images/train",
        "val":   "images/val",
        "nc":    len(classes),
        "names": classes,
    }, default_flow_style=False))

    (out_dir / "classes.json").write_text(
        __import__("json").dumps(classes, indent=2)
    )

    print(f"[prepare] {len(classes)} classes, {total_train} train, {total_val} val")
    print(f"[prepare] Dataset → {out_dir}")
    return yaml_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",     required=True, type=Path)
    parser.add_argument("--output",    required=True, type=Path)
    parser.add_argument("--val-split", type=float, default=0.2)
    args = parser.parse_args()
    prepare_dataset(args.input, args.output, args.val_split)


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/training_factory/ -v
```
Expected: PASS (all 7 tests)

**Step 5: Commit**

```bash
git add training-factory/prepare_797.py tests/training_factory/test_prepare_797.py
git commit -m "feat: prepare_797.py — YOLO dataset builder with healthy/damaged classes"
```

---

## Task 4: Update `backend/modal_app/train_yolo.py` — dynamic classes + multi-GPU

**Files:**
- Modify: `backend/modal_app/train_yolo.py`

The existing file hardcodes `COMPONENT_CLASSES` and uses `gpu="H100"`. Two changes:

**Step 1: Make classes dynamic**

In `train()`, replace the hardcoded `COMPONENT_CLASSES` write with classes read from `data.yaml`:

```python
# After loading yaml_path, read classes from it:
import yaml as _yaml
with open(yaml_path) as f:
    _meta = _yaml.safe_load(f)
_classes = _meta.get("names", COMPONENT_CLASSES)
_nc      = _meta.get("nc", len(COMPONENT_CLASSES))
```

Then replace the two uses of `COMPONENT_CLASSES` at the bottom:
```python
# was: (models_path / "classes.json").write_text(json.dumps(COMPONENT_CLASSES))
(models_path / "classes.json").write_text(json.dumps(_classes))

# was: print(f"[DONE] Classes: {COMPONENT_CLASSES}")
print(f"[DONE] Classes ({_nc}): {_classes}")
```

**Step 2: Add `n_gpus` parameter and multi-GPU device string**

Add `n_gpus: int = 1` to the `train()` function signature, and pass `device` to both `model.train()` calls:

```python
def train(
    epochs: int = 150,
    model_size: str = "s",
    imgsz: int = 640,
    batch: int = 48,
    freeze_epochs: int = 10,
    patience: int = 30,
    n_gpus: int = 1,          # ← add this
):
    device = ",".join(str(i) for i in range(n_gpus))
    ...
    # In both model.train() calls, add:
    #   device=device,
```

**Step 3: Update `main()` to override GPU spec via `with_options`**

```python
@training_app.local_entrypoint()
def main(
    epochs: int = 150,
    model_size: str = "s",
    imgsz: int = 640,
    batch: int = 48,
    freeze_epochs: int = 10,
    n_gpus: int = 1,
):
    import modal
    gpu_spec = modal.gpu.H100(count=n_gpus) if n_gpus > 1 else "H100"
    result = train.with_options(gpu=gpu_spec).remote(
        epochs=epochs,
        model_size=model_size,
        imgsz=imgsz,
        batch=batch,
        freeze_epochs=freeze_epochs,
        n_gpus=n_gpus,
    )
    print(f"\nResult: {result}")
```

**Step 4: Smoke-test the Modal app parses without error**

```bash
cd /Users/evan/Desktop/dronecat
python -c "import backend.modal_app.train_yolo"
```
Expected: no output (clean import)

**Step 5: Commit**

```bash
git add backend/modal_app/train_yolo.py
git commit -m "feat: train_yolo — dynamic classes from yaml, multi-H100 support"
```

---

## Task 5: End-to-end smoke test on a small subset

Before uploading all ~2500+ images, verify the pipeline works on 5 images.

**Step 1: Run augment on a small subset**

```bash
python training-factory/augment.py \
    --parts /Users/evan/Desktop/cat_797_parts/images \
    --damage /Users/evan/Desktop/cat-scrape/output \
    --output /tmp/cat797_aug_test \
    --variants 2
```
Expected: prints `[augment] N healthy, M damaged → /tmp/cat797_aug_test`

**Step 2: Run prepare on the augmented output**

```bash
python training-factory/prepare_797.py \
    --input  /tmp/cat797_aug_test \
    --output /tmp/cat797_dataset_test \
    --val-split 0.2
```
Expected: prints class list, train/val counts, dataset path.

**Step 3: Spot-check the dataset**

```bash
python3 - << 'EOF'
import yaml
from pathlib import Path
d = Path("/tmp/cat797_dataset_test")
meta = yaml.safe_load((d / "data.yaml").read_text())
print("Classes:", meta["names"])
print("nc:", meta["nc"])
train_imgs = list((d / "images" / "train").glob("*.jpg"))
train_lbls = list((d / "labels" / "train").glob("*.txt"))
print("Train images:", len(train_imgs), "  labels:", len(train_lbls))
assert len(train_imgs) == len(train_lbls), "image/label count mismatch!"
# Verify a label format
sample = train_lbls[0].read_text().strip()
parts = sample.split()
assert len(parts) == 5 and parts[1:] == ["0.5","0.5","1.0","1.0"], f"Bad label: {sample}"
print("Label format OK:", sample)
EOF
```
Expected: no assertion errors, classes include `_healthy`/`_damaged` variants.

---

## Task 6: Full run + upload + train

**Step 1: Run augment on full dataset**

```bash
python training-factory/augment.py \
    --parts /Users/evan/Desktop/cat_797_parts/images \
    --damage /Users/evan/Desktop/cat-scrape/output \
    --output /Users/evan/Desktop/cat-scrape/augmented \
    --variants 6
```

**Step 2: Run prepare on full augmented output**

```bash
python training-factory/prepare_797.py \
    --input  /Users/evan/Desktop/cat-scrape/augmented \
    --output data/797_dataset \
    --val-split 0.2
```

**Step 3: Upload to Modal volume**

```bash
python scripts/upload_dataset.py --dataset data/797_dataset
```

**Step 4: Launch training on 2× H100**

```bash
modal run backend/modal_app/train_yolo.py \
    --model-size m \
    --imgsz 640 \
    --epochs 100 \
    --n-gpus 2
```

Monitor in Modal dashboard. Weights land at `/models/dronecat_yolo_best.pt` on the volume.

**Step 5: Download weights**

```bash
python scripts/get_trained_model.py
```
