#!/usr/bin/env python3
"""Build a Chroma vector DB of CAT parts using SigLIP2 embeddings.
Uses sample images from HackIL26-CATrack and parts metadata from seed_parts.json.
Run once to create the local Chroma DB before demo."""

import json
import os
import sys
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CATRACK_DIR = os.path.join(DATA_DIR, "catrack_samples")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma_db")


def load_parts():
    with open(os.path.join(DATA_DIR, "seed_parts.json")) as f:
        return json.load(f)["parts"]


def image_to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def main():
    import modal
    import chromadb

    parts = load_parts()
    print(f"Loaded {len(parts)} parts from seed_parts.json")

    SigLIP2 = modal.Cls.lookup("dronecat", "SigLIP2PartsIdentifier")
    siglip2 = SigLIP2()

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    try:
        client.delete_collection("cat_parts")
    except Exception:
        pass
    collection = client.create_collection("cat_parts", metadata={"hnsw:space": "cosine"})

    count = 0
    for part in parts:
        pn = part["part_number"]
        images = part.get("sample_images", [])

        if not images:
            print(f"  [{pn}] No sample images, skipping embedding (metadata only)")
            collection.add(
                ids=[pn],
                embeddings=[[0.0] * 768],
                metadatas=[{
                    "part_number": pn,
                    "description": part["description"],
                    "compatible_models": ", ".join(part["compatible_models"]),
                    "price_usd": part["price_usd"],
                    "category": part["category"],
                }],
            )
            count += 1
            continue

        for img_rel in images:
            img_path = os.path.join(CATRACK_DIR, img_rel)
            if not os.path.exists(img_path):
                print(f"  [{pn}] Image not found: {img_path}, skipping")
                continue

            print(f"  [{pn}] Embedding {img_rel}...")
            b64 = image_to_b64(img_path)
            embedding = siglip2.embed_image.remote(b64)

            doc_id = f"{pn}_{os.path.basename(img_rel).replace(' ', '_')}"
            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                metadatas=[{
                    "part_number": pn,
                    "description": part["description"],
                    "compatible_models": ", ".join(part["compatible_models"]),
                    "price_usd": part["price_usd"],
                    "category": part["category"],
                    "source_image": img_rel,
                }],
            )
            count += 1

    print(f"\nSeeded {count} entries into Chroma at {CHROMA_DIR}")
    print("Done.")


if __name__ == "__main__":
    main()
