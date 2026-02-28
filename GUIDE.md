# CatWatch SDK Guide

AI-powered equipment inspection. Stream video from any camera to cloud AI — get real-time detections, analysis, and findings on a web dashboard.

```
Camera (SDK)  ──WebSocket──▶  Modal Backend (YOLO + Qwen)  ──WebSocket──▶  Dashboard
```

---

## 1. Get an API key

1. Go to the CatWatch dashboard (e.g. `https://catwatch.vercel.app`)
2. Sign in with your email (magic link)
3. **API Keys** in the sidebar > **Create Key**
4. Copy the key — looks like `cw_live_xxxxxxxxxxxx`

---

## 2. Install

```bash
pip install catwatch
```

Raspberry Pi with CSI camera:

```bash
pip install catwatch[picamera]
```

---

## 3. Connect and run

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")
print(f"Dashboard: {cw.dashboard_url}")
cw.run()
```

### Source types

| Type | Example | Use case |
|------|---------|----------|
| `int` | `0` | USB webcam or built-in camera |
| `str` path | `"/path/to/video.mp4"` | Pre-recorded video file |
| `str` URL | `"rtsp://192.168.1.10:8554/cam"` | RTSP / IP camera stream |
| `Picamera2` | `Picamera2()` | Raspberry Pi CSI camera |

### Modes

| Mode | Behavior |
|------|----------|
| `"general"` | General scene and safety monitoring |
| `"cat"` | CAT equipment inspection with zone-aware AI + CATrack criteria |

### Unit memory (optional)

Pass unit identity to enable cross-inspection memory:

```python
cw.connect(
    source=0,
    mode="cat",
    unit_serial="CAT325-001",   # tracked across inspections
    model="CAT 325",
    fleet_tag="fleet_alpha",    # fleet-wide pattern matching
)
```

---

## 4. Callbacks

Register before calling `cw.run()`:

```python
@cw.on_detection
def handle_detection(msg):
    for det in msg["detections"]:
        print(f"  {det['label']} ({det['confidence']:.0%}) zone={det.get('zone')}")

@cw.on_analysis
def handle_analysis(msg):
    data = msg["data"]
    print(f"[{data['severity']}] {data['description']}")

@cw.on_finding
def handle_finding(msg):
    f = msg["data"]
    print(f"[{f['rating']}] {f['zone']} — {f['description']}")

@cw.on_report
def handle_report(msg):
    print(msg["data"])

cw.run()
```

| Decorator | Fires when | Key fields |
|-----------|------------|------------|
| `@cw.on_detection` | YOLO runs (~every frame) | `detections[].label`, `.confidence`, `.bbox`, `.zone` |
| `@cw.on_analysis` | Qwen2-VL analyzes (~3s) | `data.severity`, `.description`, `.findings[]`, `.zone` |
| `@cw.on_finding` | Finding persisted | `data.rating`, `.zone`, `.description` |
| `@cw.on_voice_answer` | Voice Q&A returns | `text` |
| `@cw.on_report` | Report generated | `data` (full report JSON) |

---

## 5. Send actions

```python
# Ask about the current frame
cw.send({"type": "voice_question", "text": "Is there hydraulic fluid leaking?"})

# Generate inspection report
cw.send({
    "type": "generate_report",
    "model": "CAT 325",
    "serial": "CAT0325F4K01847",
    "hours": 2847,
    "technician": "J. Smith",
    "coverage_percent": 85,
})

# Switch mode mid-session
cw.send({"type": "set_mode", "mode": "general"})
```

---

## 6. Raspberry Pi setup

```bash
# System deps
sudo apt update && sudo apt install -y python3-pip python3-venv libcap-dev

# Venv
python3 -m venv ~/catwatch-env && source ~/catwatch-env/bin/activate

# Install
pip install catwatch            # USB camera
pip install catwatch[picamera]  # CSI ribbon camera
```

### CSI camera example

```python
from picamera2 import Picamera2
from catwatch import CatWatch

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (1280, 720)}))
cam.start()

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=cam, mode="cat", unit_serial="DRONE-PI-001")
print(f"Dashboard: {cw.dashboard_url}")
cw.run()
```

### Run on boot (systemd)

```ini
# /etc/systemd/system/catwatch.service
[Unit]
Description=CatWatch Inspection
After=network-online.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi
ExecStart=/home/pi/catwatch-env/bin/python /home/pi/inspect.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable catwatch && sudo systemctl start catwatch
```

---

## 7. Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: catwatch` | `pip install catwatch` (or `pip install -e path/to/sdk`) |
| `cv2` import error | `pip install opencv-python` |
| "Invalid API key" | Create a key in Dashboard > API Keys |
| HTTP 404 on connect | Backend not deployed — see DEV.md |
| No VLM analysis | YOLO needs to detect equipment first — point camera at a CAT machine |
| Dashboard video blank | Backend URL mismatch — check `NEXT_PUBLIC_BACKEND_WS` |
