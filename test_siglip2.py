import base64
import io
from backend.modal_app.siglip2 import SigLIP2PartsIdentifier
from PIL import Image

img = Image.new("RGB", (384, 384), color=(128, 128, 128))
buf = io.BytesIO()
img.save(buf, format="JPEG")
b64 = base64.b64encode(buf.getvalue()).decode()

s = SigLIP2PartsIdentifier()
results = s.triage_crops.remote([b64], ["test_label"], threshold=0.05)
print(results)
