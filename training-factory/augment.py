#!/usr/bin/env python3
"""
Augment CAT 797 part images (healthy originals + Nano Banana damage variants).

Cross-references:
  --parts  : cat_797_parts/images/<category>/<Part (SKU)>.jpg  (185 originals)
  --damage : cat-scrape/output/<category>/<Part (SKU)>/        (done + *.png)

Output layout:
  <output>/healthy/<category>/<stem>_aug<N>.jpg
  <output>/damaged/<category>/<stem>_<damage_stem>_aug<N>.jpg

Usage:
    python training-factory/augment.py \
        --parts  ~/Desktop/cat_797_parts/images \
        --damage ~/Desktop/cat-scrape/output \
        --output ~/Desktop/cat-scrape/augmented \
        --variants 6
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image


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
        variants = sorted(dmg_dir.glob("*.png")) if dmg_dir.exists() else []
        if (dmg_dir / "done").exists() and variants:
            matched.append((img, variants))
        else:
            unmatched.append(img)
    return matched, unmatched


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
        A.RandomShadow(p=0.2),
        A.OneOf([
            A.HorizontalFlip(),
            A.VerticalFlip(),
            A.RandomRotate90(),
        ], p=0.7),
        A.OneOf([
            A.ShiftScaleRotate(shift_limit=0.1, scale_limit=0.2, rotate_limit=30, border_mode=0),
            A.Perspective(scale=(0.05, 0.1)),
        ], p=0.4),
    ])


def _augment_image(img_path: Path, out_dir: Path, stem: str, n: int, pipeline) -> list:
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
    pipeline = _build_pipeline()
    matched, unmatched = cross_reference(parts_dir, damage_dir)
    total_healthy = total_damaged = 0

    for orig, dmg_imgs in matched:
        cat = orig.parent.name
        total_healthy += len(_augment_image(orig, out_dir / "healthy" / cat, orig.stem, variants, pipeline))
        for dmg in dmg_imgs:
            stem = f"{orig.stem}_{dmg.stem}"
            total_damaged += len(_augment_image(dmg, out_dir / "damaged" / cat, stem, variants, pipeline))

    for orig in unmatched:
        cat = orig.parent.name
        total_healthy += len(_augment_image(orig, out_dir / "healthy" / cat, orig.stem, variants, pipeline))

    print(f"[augment] {total_healthy} healthy, {total_damaged} damaged → {out_dir}")


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
