from pathlib import Path
import pytest


def test_cross_reference_matched(tmp_path):
    """Parts with a done damage dir should be matched."""
    from augment import cross_reference

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
    from augment import cross_reference

    parts = tmp_path / "parts" / "Hydraulics"
    parts.mkdir(parents=True)
    (parts / "Pump Assembly (888-0001).jpg").write_bytes(b"img")

    matched, unmatched = cross_reference(tmp_path / "parts", tmp_path / "damage")
    assert len(matched) == 0
    assert len(unmatched) == 1


import numpy as np
from PIL import Image as PILImage


def _make_jpg(path, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    PILImage.fromarray(np.random.randint(0, 255, (*size, 3), dtype=np.uint8)).save(path, format="JPEG")


def test_augment_matched_part_produces_variants(tmp_path):
    from augment import augment_dataset
    orig = tmp_path / "parts" / "Engine" / "Fuel Pump (123-4567).jpg"
    _make_jpg(orig)
    dmg_dir = tmp_path / "damage" / "Engine" / "Fuel Pump (123-4567)"
    dmg_dir.mkdir(parents=True)
    (dmg_dir / "done").write_text("{}")
    _make_jpg(dmg_dir / "fuel_pump_wear_1.png")
    out = tmp_path / "augmented"
    augment_dataset(tmp_path / "parts", tmp_path / "damage", out, variants=3)
    assert len(list((out / "healthy" / "Engine").glob("*.jpg"))) == 3
    assert len(list((out / "damaged" / "Engine").glob("*.jpg"))) == 3


def test_augment_unmatched_produces_healthy_only(tmp_path):
    from augment import augment_dataset
    orig = tmp_path / "parts" / "Hydraulics" / "Pump (000-0001).jpg"
    _make_jpg(orig)
    out = tmp_path / "augmented"
    augment_dataset(tmp_path / "parts", tmp_path / "damage", out, variants=2)
    assert len(list((out / "healthy" / "Hydraulics").glob("*.jpg"))) == 2
    damaged = list((out / "damaged").rglob("*.jpg")) if (out / "damaged").exists() else []
    assert len(damaged) == 0
