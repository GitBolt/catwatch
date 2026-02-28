# Entry point for Modal deployment.
# Usage: modal deploy modal_deploy.py

from backend.modal_app import app  # noqa: F401 — registers the Modal app
from backend.modal_app.yolo_detector import YoloDetector  # noqa: F401
from backend.modal_app.qwen_vl import Qwen25VLInspector  # noqa: F401
from backend.modal_app.siglip2 import SigLIP2PartsIdentifier  # noqa: F401
from backend.modal_app.orchestrator import web  # noqa: F401
