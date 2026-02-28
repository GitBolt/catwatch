# CatWatch SDK

Drone inspection SDK for the CatWatch platform.

## Install

```bash
pip install catwatch
```

## Usage

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0)  # 0 = webcam, RTSP url, or picamera2 object
print(cw.dashboard_url)

@cw.on_detection
def on_det(msg):
    print(f"{len(msg['detections'])} detections")

@cw.on_analysis
def on_analysis(msg):
    print(f"[{msg['data']['severity']}] {msg['data']['description']}")

cw.run()
```
