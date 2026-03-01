from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "training-factory"))

import numpy as np
from PIL import Image as PILImage
import yaml


def _write_img(path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.fromarray(np.random.randint(0, 255, (*size, 3), dtype=np.uint8)).save(path, format="JPEG")


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
    prepare_dataset(aug, out, val_split=0.0)
    meta = yaml.safe_load((out / "data.yaml").read_text())
    assert meta["nc"] == len(meta["names"])
    assert "engine_healthy" in meta["names"]
    assert "engine_damaged" in meta["names"]
    assert "hydraulics_healthy" in meta["names"]
    imgs = list((out / "images" / "train").glob("*.jpg"))
    assert len(imgs) > 0
    for img in imgs:
        lbl = out / "labels" / "train" / img.with_suffix(".txt").name
        assert lbl.exists()
        parts = lbl.read_text().strip().split()
        assert len(parts) == 5
        assert parts[1:] == ["0.5", "0.5", "1.0", "1.0"]


def test_val_split_respected(tmp_path):
    from prepare_797 import prepare_dataset
    aug = tmp_path / "augmented" / "healthy" / "Engine"
    aug.mkdir(parents=True)
    for i in range(10):
        _write_img(aug / f"part_aug{i}.jpg")
    out = tmp_path / "dataset"
    prepare_dataset(tmp_path / "augmented", out, val_split=0.2)
    assert len(list((out / "images" / "val").glob("*.jpg"))) == 2
    assert len(list((out / "images" / "train").glob("*.jpg"))) == 8
