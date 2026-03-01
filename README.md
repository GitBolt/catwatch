# CatWatch

AI-powered equipment inspection platform. Stream video from any camera to cloud AI, get real-time object detection and visual analysis on a live dashboard.

The SDK connects a camera (webcam, drone, Raspberry Pi, RTSP) to a GPU backend running YOLO + Qwen2-VL on Modal. An operator watches the live feed on a web dashboard with bounding boxes, AI analysis, voice Q&A, and inspection reports.

```
Camera (SDK)  --WebSocket-->  Modal Backend (YOLO + Qwen VLM)  --WebSocket-->  Dashboard
```

---

## Getting started

1. Sign in at the CatWatch dashboard with your email (magic link)
2. Go to **API Keys > Create Key** and copy the key (looks like `cw_live_xxxxxxxxxxxx`)
3. Install the SDK:

```bash
pip install catwatch
```

4. Run:

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")
print(f"Dashboard: {cw.dashboard_url}")
cw.run()
```

Open the printed dashboard URL in a browser to see the live inspection.

---

## Modes

**`"general"`** — general safety and scene monitoring. Uses vanilla YOLOv8.

**`"cat"`** — CAT equipment inspection with a fine-tuned YOLO model and CATrack criteria. The VLM auto-identifies the equipment type and builds a dynamic zone checklist.

Only one inspection runs at a time per user. Starting a new session automatically closes any previous one.

---

## Sources

`source` can be:
- `0` — USB webcam or built-in camera
- `"/path/to/video.mp4"` — pre-recorded video file
- `"rtsp://192.168.1.10:8554/cam"` — RTSP / IP camera stream
- A `Picamera2` object — Raspberry Pi CSI camera

---

## Memory across inspections

Pass identity so the AI remembers past inspections of the same unit or site:

```python
# CAT mode — equipment serial
cw.connect(source=0, mode="cat", unit_serial="CAT325-001", model="CAT 325", fleet_tag="fleet_alpha")

# General mode — site name
cw.connect(source=0, mode="general", location="warehouse-7B")
```

If you don't pass `unit_serial` or `location`, the dashboard falls back to browser geolocation so inspections at the same physical location share memory automatically.

On later inspections of the same unit or site, the dashboard shows prior findings, and the VLM analysis is primed with historical context. Fleet-wide patterns are surfaced across units with the same `fleet_tag`.

---

## Callbacks

Register before calling `cw.run()`:

```python
@cw.on_detection
def handle_detection(msg):
    for det in msg["detections"]:
        print(f"  {det['label']} ({det['confidence']:.0%})")

@cw.on_analysis
def handle_analysis(msg):
    data = msg["data"]
    print(f"[{data['severity']}] {data['description']}")

@cw.on_finding
def handle_finding(msg):
    f = msg["data"]
    print(f"[{f['rating']}] {f['zone']} — {f['description']}")

@cw.on_session_ended
def handle_ended(msg):
    print("Session ended by operator")

cw.run()
```

Available callbacks: `on_detection` (YOLO, every frame), `on_analysis` (VLM, every ~3s), `on_finding` (persisted finding), `on_voice_answer` (voice Q&A response), `on_report` (generated report), `on_viewer_joined`, `on_mode_change`, `on_session_ended`.

---

## Actions

```python
# Ask about the current frame
cw.ask("Is there hydraulic fluid leaking?")

# Generate an inspection report
cw.generate_report(model="CAT 325", serial="CAT0325F4K01847")

# Switch mode mid-session
cw.set_mode("general")

# Send raw payload
cw.send({"type": "voice_question", "text": "What's the condition of the tracks?"})
```

---

## Dashboard

Once the SDK is streaming, the dashboard shows:

- **Live video feed** with YOLO bounding boxes overlaid
- **VLM analysis panel** — severity, description, confidence, with severity trend tracking across repeated analyses of the same zone
- **AI Insights** — cross-signal correlations (e.g. YOLO detects a hydraulic hose + VLM mentions fluid stain = "possible hydraulic leak")
- **Zone checklist** — in CAT mode, the VLM identifies equipment and builds a dynamic checklist. In general mode, zones appear as they're discovered
- **Voice Q&A** — mic button on the video feed to ask questions about what the camera sees
- **Unit/Site Memory** — history from prior inspections of the same unit or location
- **End Inspection** — stops the session and shuts down the SDK connection

After an inspection, view the full report (PDF or JSON), all findings (filterable by severity), and fleet-wide similar findings from the Inspections page.

---

## Raspberry Pi

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv libcap-dev
python3 -m venv ~/catwatch-env && source ~/catwatch-env/bin/activate
pip install catwatch[picamera]
```

```python
from picamera2 import Picamera2
from catwatch import CatWatch

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (1280, 720)}))
cam.start()

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=cam, mode="cat", unit_serial="DRONE-PI-001")
cw.run()
```

To run on boot, create a systemd service at `/etc/systemd/system/catwatch.service`:

```ini
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

## Stack

- **SDK**: Python — OpenCV, websockets, numpy
- **Backend**: Modal (T4 for YOLO, A100 for Qwen2-VL + Whisper), FastAPI orchestrator
- **Frontend**: Next.js 15 on Vercel, PostgreSQL via Prisma, magic link auth
- **Memory**: Supermemory for cross-inspection knowledge

See [DEV.md](DEV.md) for the developer guide (deploying, environment setup, architecture details).

---

## Troubleshooting

- **`ModuleNotFoundError: catwatch`** — run `pip install catwatch`
- **"Invalid API key"** — create a key in Dashboard > API Keys
- **No VLM analysis** — YOLO needs to detect something first, and the dashboard must be open (GPU only runs when a viewer is connected)
- **Dashboard video blank** — check that `NEXT_PUBLIC_BACKEND_WS` matches your Modal deployment URL
- **Supermemory empty on second run** — make sure `SUPERMEMORY_API_KEY` is set in your web `.env.local`
