import base64
import io
import modal

from . import app, yolo_image


@app.cls(
    gpu="T4",
    image=yolo_image,
    min_containers=1,
    scaledown_window=600,
)
class YoloDetector:
    @modal.enter()
    def load(self):
        from ultralytics import YOLO
        self.model = YOLO("yolov8n.pt")
        print("[YoloDetector] Loaded yolov8n on T4.")

    @modal.method()
    def detect(self, frame_b64):
        from PIL import Image
        import time

        img_bytes = base64.b64decode(frame_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        t0 = time.time()
        results = self.model(image, verbose=False)
        inference_ms = round((time.time() - t0) * 1000, 1)

        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "label": r.names[int(box.cls[0])],
                    "confidence": round(float(box.conf[0]), 3),
                    "bbox": [
                        round(x1 / image.width, 4),
                        round(y1 / image.height, 4),
                        round(x2 / image.width, 4),
                        round(y2 / image.height, 4),
                    ],
                })

        return {"detections": detections, "count": len(detections), "yolo_ms": inference_ms}
