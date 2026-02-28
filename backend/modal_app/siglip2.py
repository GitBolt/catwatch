import base64
import modal

from . import app, siglip_image


@app.cls(
    gpu=modal.gpu.A10G(),
    image=siglip_image,
    container_idle_timeout=120,
)
class SigLIP2PartsIdentifier:
    @modal.enter()
    def load(self):
        from transformers import AutoProcessor, AutoModel
        import torch

        model_id = "google/siglip2-so400m-patch14-384"
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id, torch_dtype=torch.float16).to("cuda")
        self.model.eval()

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
