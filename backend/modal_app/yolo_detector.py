import base64
import io
import modal

from . import app, yolo_image, models_volume


@app.cls(
    gpu="T4",
    image=yolo_image,
    min_containers=1,
    scaledown_window=600,
    volumes={"/models": models_volume},
)
class YoloDetector:
    @modal.enter()
    def load(self):
        from pathlib import Path
        from ultralytics import YOLO

        self.general_model = YOLO("yolov8n.pt")
        print("[YoloDetector] Loaded vanilla yolov8n for general mode.")

        custom = Path("/models/dronecat_yolo_best.pt")
        if custom.exists():
            self.cat_model = YOLO(str(custom))
            print("[YoloDetector] Loaded fine-tuned dronecat model for cat mode.")
        else:
            self.cat_model = self.general_model
            print("[YoloDetector] No custom model found — cat mode will use yolov8n fallback.")

    @modal.method()
    def detect(self, frame_b64, mode="general"):
        from PIL import Image
        import time

        model = self.cat_model if mode == "797" else self.general_model

        img_bytes = base64.b64decode(frame_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        t0 = time.time()
        results = model(image, verbose=False)
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


@app.cls(
    gpu="T4",
    image=yolo_image,
    min_containers=0,
    scaledown_window=300,
    volumes={"/models": models_volume},
)
class YoloDetector797:
    @modal.enter()
    def load(self):
        from pathlib import Path
        from ultralytics import YOLO

        custom = Path("/models/797_yolo_best.pt")
        if custom.exists():
            self.model = YOLO(str(custom))
            print("[YoloDetector797] Loaded 797 damage model from volume.")
        else:
            self.model = YOLO("yolov8n.pt")
            print("[YoloDetector797] No 797 model found — using yolov8n fallback.")

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
