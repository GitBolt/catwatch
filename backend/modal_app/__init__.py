import modal

app = modal.App("dronecat")

# Persistent volume for trained model weights shared between training and inference.
models_volume = modal.Volume.from_name("dronecat-models", create_if_missing=True)


def _download_yolo():
    from ultralytics import YOLO
    YOLO("yolov8n.pt")


yolo_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "ultralytics", "torch", "torchvision",
        "Pillow", "numpy", "opencv-python-headless",
    )
    .run_function(_download_yolo)
)


qwen_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers", "torch", "torchvision",
        "accelerate", "qwen-vl-utils", "Pillow", "numpy",
    )
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi", "uvicorn[standard]",
        "websockets", "requests", "Pillow",
        "asyncpg",
    )
    .add_local_dir("data", remote_path="/root/data")
)
