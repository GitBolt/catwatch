import base64
import modal

from . import app, florence2_image


@app.cls(
    gpu=modal.gpu.T4(),
    image=florence2_image,
    keep_warm=1,
    container_idle_timeout=600,
)
class Florence2Processor:
    @modal.enter()
    def load(self):
        from transformers import AutoProcessor, AutoModelForCausalLM
        import torch

        model_id = "microsoft/Florence-2-base"
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True, torch_dtype=torch.float16
        ).to("cuda")
        self.model.eval()

    @modal.method()
    def process_frame(self, frame_b64):
        from PIL import Image
        import io
        import torch

        img_bytes = base64.b64decode(frame_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        prompt = "<OD>"
        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to("cuda")

        with torch.no_grad():
            generated = self.model.generate(
                **inputs,
                max_new_tokens=1024,
                num_beams=3,
            )

        result = self.processor.batch_decode(generated, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(
            result, task=prompt, image_size=(image.width, image.height)
        )

        detections = []
        od = parsed.get("<OD>", {})
        bboxes = od.get("bboxes", [])
        labels = od.get("labels", [])

        for bbox, label in zip(bboxes, labels):
            x1 = bbox[0] / image.width
            y1 = bbox[1] / image.height
            x2 = bbox[2] / image.width
            y2 = bbox[3] / image.height
            detections.append({
                "label": label,
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.85,
            })

        return detections
