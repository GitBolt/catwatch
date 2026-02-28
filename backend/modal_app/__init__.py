import modal

app = modal.App("dronecat")

florence2_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch", "torchvision", "transformers",
        "Pillow", "numpy", "accelerate",
    )
)

whisper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch", "transformers",
        "Pillow", "numpy", "accelerate",
    )
)

vllm_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "vllm", "torch", "transformers",
        "Pillow", "numpy",
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
)
