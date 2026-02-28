import base64
import modal

from . import app, siglip_image

# ── Triage prompt sets (pre-computed once at container startup) ────────────

_TRIAGE_NORMAL_PROMPTS = [
    # Ground level
    "intact track shoe", "clean final drive housing", "properly tensioned track chain",
    "undamaged track roller", "clean carbody underside", "intact sprocket teeth",
    # Middle level
    "intact hydraulic hose", "clean cab exterior", "undamaged handrail",
    "clear work light lens", "dry hydraulic pump housing",
    # Upper level
    "clean exhaust stack", "intact turbocharger housing", "tight fan belt",
    "clean radiator fins", "clear air filter housing",
    # Implement
    "smooth cylinder rod surface", "intact boom pin", "full set of bucket teeth",
    "tight stick pin bore", "undamaged wear plate",
]

_TRIAGE_ANOMALY_PROMPTS = [
    # Ground level
    "worn track shoe", "leaking final drive seal", "loose track chain",
    "damaged track roller", "fluid puddle under machine", "cracked carbody weld",
    "missing sprocket tooth", "loose bolt on undercarriage",
    # Middle level
    "leaking hydraulic fitting", "cracked cab glass", "bent handrail",
    "broken work light", "hydraulic weepage on pump", "corroded paint surface",
    "damaged seal",
    # Upper level
    "black exhaust smoke", "white exhaust smoke", "blue exhaust smoke",
    "oil leak on turbocharger", "frayed fan belt", "clogged radiator fins",
    "debris in cooling system",
    # Implement
    "scored cylinder rod", "elongated pin bore", "missing bucket tooth",
    "cracked boom weld", "worn bucket cutting edge", "hydraulic leak at cylinder seal",
    # General
    "rust", "corrosion", "crack", "dent", "leak", "missing part",
    "broken component", "excessive wear",
]


@app.cls(
    gpu="T4",
    image=siglip_image,
    min_containers=1,
    scaledown_window=120,
)
class SigLIP2PartsIdentifier:
    @modal.enter()
    def load(self):
        from transformers import SiglipProcessor, SiglipModel
        import torch

        model_id = "google/siglip2-so400m-patch14-384"
        # Use direct Siglip classes — AutoProcessor has a tokenizer-resolution bug
        # with newer transformers versions for SigLIP2.
        self.processor = SiglipProcessor.from_pretrained(model_id)
        self.model = SiglipModel.from_pretrained(model_id, torch_dtype=torch.float16).to("cuda")
        self.model.eval()

        print("[SigLIP2] Pre-computing triage text embeddings...")
        self._normal_embeddings = self._encode_texts(_TRIAGE_NORMAL_PROMPTS)
        self._anomaly_embeddings = self._encode_texts(_TRIAGE_ANOMALY_PROMPTS)
        print(
            f"[SigLIP2] Ready. {len(_TRIAGE_NORMAL_PROMPTS)} normal, "
            f"{len(_TRIAGE_ANOMALY_PROMPTS)} anomaly prompts embedded."
        )

    def _encode_texts(self, texts):
        """Encode a list of text prompts into L2-normalized float32 numpy embeddings."""
        import torch
        import numpy as np

        inputs = self.processor(
            text=texts,
            return_tensors="pt",
            padding="max_length",
            max_length=64,
            truncation=True,
        ).to("cuda")
        with torch.no_grad():
            features = self.model.get_text_features(**inputs)
        features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().float().numpy()  # [n_texts, embed_dim]

    @modal.method()
    def triage_crops(self, crops_b64, yolo_labels, threshold=0.05):
        """
        Tier 2 anomaly triage on a batch of YOLO crops.

        Args:
            crops_b64: list of base64-encoded JPEG images (padded & resized to 384×384)
            yolo_labels: list of YOLO class labels (same length, unused currently but
                         reserved for zone-specific prompt filtering)
            threshold: anomaly_score threshold above which a crop is flagged

        Returns:
            list of dicts with anomaly_score, is_flagged, top_anomaly_match, top_normal_match
        """
        from PIL import Image
        import io
        import torch
        import numpy as np

        if not crops_b64:
            return []

        images = []
        for b64 in crops_b64:
            img_bytes = base64.b64decode(b64)
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            images.append(img)

        # Batch image encoding
        inputs = self.processor(images=images, return_tensors="pt").to("cuda")
        with torch.no_grad():
            image_features = self.model.get_image_features(**inputs)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        image_np = image_features.cpu().float().numpy()  # [n_crops, embed_dim]

        # Cosine similarities against pre-computed text embeddings
        normal_sims = image_np @ self._normal_embeddings.T    # [n_crops, n_normal]
        anomaly_sims = image_np @ self._anomaly_embeddings.T  # [n_crops, n_anomaly]

        results = []
        for i in range(len(crops_b64)):
            max_normal_idx = int(np.argmax(normal_sims[i]))
            max_anomaly_idx = int(np.argmax(anomaly_sims[i]))
            anomaly_score = float(anomaly_sims[i, max_anomaly_idx]) - float(normal_sims[i, max_normal_idx])
            results.append({
                "anomaly_score": round(anomaly_score, 4),
                "is_flagged": anomaly_score > threshold,
                "top_anomaly_match": _TRIAGE_ANOMALY_PROMPTS[max_anomaly_idx],
                "top_normal_match": _TRIAGE_NORMAL_PROMPTS[max_normal_idx],
            })

        flagged = sum(1 for r in results if r["is_flagged"])
        print(f"[SigLIP2] Triaged {len(crops_b64)} crops, {flagged} flagged (threshold={threshold})")
        return results

    @modal.method()
    def embed_image(self, image_b64):
        from PIL import Image
        import io
        import torch

        img_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        inputs = self.processor(images=image, return_tensors="pt").to("cuda")
        with torch.no_grad():
            outputs = self.model.get_image_features(**inputs)

        embedding = outputs[0].cpu().numpy().tolist()
        return embedding

    @modal.method()
    def identify_part(self, image_b64, chroma_host="localhost", chroma_port=8000):
        import chromadb

        embedding = self.embed_image.local(image_b64)

        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        collection = client.get_collection("cat_parts")

        results = collection.query(
            query_embeddings=[embedding],
            n_results=5,
        )

        parts = []
        if results and results["ids"]:
            for i, part_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 1.0
                certainty = max(0, 1.0 - distance)
                parts.append({
                    "part_number": meta.get("part_number", part_id),
                    "description": meta.get("description", ""),
                    "compatible_models": meta.get("compatible_models", ""),
                    "price_usd": meta.get("price_usd", 0),
                    "certainty_pct": round(certainty * 100, 1),
                })

        return parts
