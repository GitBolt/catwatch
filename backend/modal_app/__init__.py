import modal

app = modal.App("dronecat")


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

whisper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch", "transformers",
        "Pillow", "numpy", "accelerate",
    )
)

qwen_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers", "torch", "torchvision",
        "accelerate", "qwen-vl-utils", "Pillow", "numpy",
    )
)

siglip_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch", "torchvision", "transformers",
        "Pillow", "numpy", "chromadb",
    )
)

web_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi", "uvicorn[standard]",
        "websockets", "requests",
    )
    .add_local_dir("data", remote_path="/root/data")
)
