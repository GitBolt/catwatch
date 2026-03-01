# CatWatch — User Guide

AI-powered equipment inspection. Stream video from any camera to cloud AI, get real-time detections and analysis on a live dashboard.

```
Camera (SDK)  ──WebSocket──▶  Modal Backend (YOLO + Qwen VLM)  ──WebSocket──▶  Dashboard
```

---

## 1. Get an API key

Go to the CatWatch dashboard, sign in with your email (magic link), then **API Keys > Create Key**. Copy the key — it looks like `cw_live_xxxxxxxxxxxx`.

---

## 2. Install

```bash
pip install catwatch
```

For Raspberry Pi with a CSI ribbon camera:

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

**Source** can be `0` (webcam), a file path, an RTSP URL, or a `Picamera2` object.

**Mode** is either `"general"` (safety monitoring, vanilla YOLO) or `"cat"` (CAT equipment inspection with fine-tuned YOLO + CATrack criteria).

Only one inspection runs at a time. Starting a new session automatically closes any previous one.

---

## 4. Memory across inspections

Pass identity so the AI remembers past inspections of the same unit or site:

```python
# CAT mode — pass equipment serial
cw.connect(
    source=0,
    mode="cat",
    unit_serial="CAT325-001",
    model="CAT 325",
    fleet_tag="fleet_alpha",
)

# General mode — pass a site name
cw.connect(
    source=0,
    mode="general",
    location="warehouse-7B",
)
```

If you don't pass `unit_serial` or `location`, the dashboard will try to use browser geolocation as a fallback so inspections at the same physical location share memory automatically.

On the second inspection of the same unit or site, the dashboard shows prior findings, and the VLM is primed with historical context.

---

## 5. Callbacks

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

Available callbacks: `on_detection` (YOLO, every frame), `on_analysis` (VLM, every ~3s), `on_finding` (persisted finding), `on_voice_answer` (voice Q&A response), `on_report` (generated report), `on_session_ended` (operator ended from dashboard).

---

## 6. Send actions

```python
# Ask about the current frame
cw.send({"type": "voice_question", "text": "Is there hydraulic fluid leaking?"})

# Generate report
cw.send({"type": "generate_report", "model": "CAT 325", "serial": "CAT0325F4K01847"})

# Switch mode mid-session
cw.set_mode("general")
```

---

## 7. Dashboard features

Once the SDK is streaming, open the dashboard URL to see:

- **Live video feed** with YOLO bounding boxes overlaid
- **VLM analysis panel** showing severity, description, and confidence — with severity trend tracking across multiple analyses of the same zone
- **AI Insights** — cross-signal correlations (e.g. YOLO sees a hydraulic hose + VLM mentions fluid stain = "possible hydraulic leak")
- **Zone checklist** — in CAT mode, the VLM identifies the equipment type and builds a dynamic checklist. In general mode, zones appear as they're discovered.
- **Voice Q&A** — click the mic button on the video feed to ask questions about what the camera sees
- **Unit/Site Memory** — shows history from prior inspections
- **End Inspection** button to stop the session, which also shuts down the SDK connection

After an inspection, view the full report (PDF or JSON), all findings, and fleet-wide similar findings from the Inspections page.

---

## 8. Raspberry Pi setup

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

## 9. Troubleshooting

- **`ModuleNotFoundError: catwatch`** — run `pip install catwatch`
- **"Invalid API key"** — create a key in Dashboard > API Keys
- **No VLM analysis** — YOLO needs to detect something first, and the dashboard must be open (GPU only runs when a viewer is connected)
- **Dashboard video blank** — check that `NEXT_PUBLIC_BACKEND_WS` matches your Modal deployment URL
- **Supermemory empty on second run** — make sure `SUPERMEMORY_API_KEY` is set in your web `.env.local`
