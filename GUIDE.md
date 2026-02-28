# CatWatch Guide

## Overview

CatWatch is an AI-powered equipment inspection platform. A camera (on a drone, Raspberry Pi, or laptop) streams video to a cloud backend that runs object detection (YOLO) and visual analysis (Qwen2-VL) in real time. An operator watches the live feed, detections, and AI findings on a web dashboard.

```
Camera (SDK)  ──WebSocket──▶  Modal Backend (YOLO + Qwen)  ──WebSocket──▶  Dashboard
```

---

## 1. Sign up and get an API key

1. Go to the CatWatch dashboard at your deployment URL (e.g. `https://catwatch-hackillinois.vercel.app`).
2. Sign in with your email — you'll receive a one-time code.
3. Navigate to **API Keys** in the sidebar.
4. Enter a name for your key (e.g. `"pi-drone"`) and click **Create Key**.
5. Copy the key. It looks like `cw_live_xxxxxxxxxxxx`.

This key authenticates your device when it connects to the inspection backend.

---

## 2. Install the SDK

The SDK runs on any machine with Python 3.9+ and a camera. Typical targets are a Raspberry Pi 5, a laptop, or any Linux SBC.

```bash
pip install catwatch
```

If you're on a Raspberry Pi with a CSI ribbon camera, also install picamera2 support:

```bash
pip install catwatch[picamera]
```

Dependencies installed automatically: `opencv-python`, `websockets`, `numpy`.

---

## 3. Connect and run

### Minimal example (USB webcam or laptop camera)

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")
cw.run()
```

`source` accepts three types:

| Type | Example | Use case |
|------|---------|----------|
| `int` | `0` | USB webcam or built-in camera (OpenCV index) |
| `str` | `"rtsp://192.168.1.10:8554/cam"` | RTSP stream or video file path |
| `picamera2` object | `Picamera2()` | Raspberry Pi CSI camera |

`mode` controls the inspection behavior:

| Mode | Behavior |
|------|----------|
| `"general"` | General scene and safety monitoring |
| `"cat"` | CAT equipment inspection with zone-aware prompts and CATrack criteria |

### Raspberry Pi with CSI camera

```python
from picamera2 import Picamera2
from catwatch import CatWatch

cam = Picamera2()
cam.configure(cam.create_video_configuration(main={"size": (1280, 720)}))
cam.start()

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=cam, mode="cat")
cw.run()
```

### RTSP stream (e.g. IP camera on the drone)

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source="rtsp://192.168.1.10:8554/live", mode="cat")
cw.run()
```

### Pre-recorded video file

```python
cw.connect(source="/path/to/inspection_video.mp4", mode="cat")
cw.run()
```

---

## 4. React to events

The SDK fires callbacks as the backend processes frames. Register them with decorators before calling `cw.run()`.

```python
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")

@cw.on_detection
def handle_detection(msg):
    for det in msg["detections"]:
        print(f"  {det['label']} ({det['confidence']:.0%}) zone={det.get('zone')}")

@cw.on_analysis
def handle_analysis(msg):
    data = msg["data"]
    print(f"[{data['severity']}] {data['description']}")
    for finding in data.get("findings", []):
        print(f"  → {finding}")

@cw.on_finding
def handle_finding(msg):
    f = msg["data"]
    print(f"Finding: [{f['rating']}] {f['zone']} — {f['description']}")

@cw.on_report
def handle_report(msg):
    print("Inspection report received:")
    print(msg["data"])

cw.run()
```

### Available callbacks

| Decorator | Fires when | Payload highlights |
|-----------|------------|-------------------|
| `@cw.on_detection` | YOLO runs on a frame (~every frame) | `detections[]` with `label`, `confidence`, `bbox`, `zone` |
| `@cw.on_analysis` | Qwen2-VL analyzes a frame (~every 3s) | `data.severity` (GREEN/YELLOW/RED), `data.description`, `data.findings[]`, `data.zone` |
| `@cw.on_finding` | A finding is persisted | `data.rating`, `data.zone`, `data.description` |
| `@cw.on_voice_answer` | Voice Q&A answer returns | `text` — the spoken answer |
| `@cw.on_report` | Full inspection report generated | `data` — the complete report |

---

## 5. Send actions

You can send commands to the backend through the WebSocket at any time during `cw.run()`:

```python
# Ask a question about what the camera sees
cw.send({"type": "voice_question", "text": "Is there hydraulic fluid leaking?"})

# Generate an inspection report
cw.send({
    "type": "generate_report",
    "model": "CAT 325",
    "serial": "CAT0325F4K01847",
    "hours": 2847,
    "technician": "J. Smith",
    "coverage_percent": 85,
})

# Switch inspection mode
cw.send({"type": "set_mode", "mode": "cat"})
```

---

## 6. Session lifecycle — how an inspection connects to the UI

The SDK on the drone **initiates** every inspection. The dashboard is a live viewer
and historical record — there is no "start inspection" button on the web UI. Here is
the full lifecycle:

### Step 1: SDK creates a session

When you call `cw.connect()`, the SDK sends a `POST /api/sessions` request to the
Modal backend with your API key and mode. The backend:

- Validates the API key against the database
- Creates a new session row (status: `active`)
- Returns a `session_id`, a `dashboard_url`, and a `ws_url`

```python
cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")

print(cw.session_id)     # → "a1b2c3d4e5f6"
print(cw.dashboard_url)  # → "https://catwatch-hackillinois.vercel.app/session/a1b2c3d4e5f6"
```

At this point the session exists but no frames are flowing yet.

### Step 2: SDK starts streaming frames

`cw.run()` enters a blocking loop that captures frames from the camera, applies
quality gates (blur, motion, rate limit), JPEG-encodes, and sends them over the
WebSocket at `/ws/ingest/{session_id}`.

The backend receives each frame and does two things simultaneously:
1. **Relays the frame** to all connected dashboard viewers (instant)
2. **Runs YOLO** on the frame, then **runs Qwen2-VL** every ~3 seconds

Results (detections, analysis, findings) are sent to both the SDK and the dashboard
in real time.

### Step 3: Operator opens the dashboard

The operator (or anyone with the link) opens `cw.dashboard_url` in a browser. The
dashboard connects to `/ws/view/{session_id}` and immediately starts receiving:

- `frame` — live video (rendered on a canvas)
- `detection` — YOLO bounding boxes (overlaid on video)
- `analysis` — Qwen2-VL severity + description (shown in a panel)
- `zone_first_seen` — zone coverage updates
- `finding` — persisted findings

The dashboard can also **send actions** back through the same WebSocket:

| Dashboard action | What happens |
|------------------|-------------|
| Click **mic button** | Sends `voice_question` → Qwen answers based on the current frame |
| Click **Generate Report** | Sends `generate_report` → Qwen generates a full inspection report |
| Toggle **General / CAT** | Sends `set_mode` → switches inspection mode live |

These actions are forwarded through the backend and processed against the latest
frame from the drone — the operator doesn't need to be running the SDK to trigger
them, they just need an active session with frames flowing.

### Step 4: Inspection ends

The session ends when any of these happen:

| Trigger | What happens |
|---------|-------------|
| `cw.stop()` called in Python | SDK closes the WebSocket gracefully |
| `Ctrl+C` on the SDK script | SDK catches `KeyboardInterrupt`, calls `stop()` |
| SDK process killed / Pi loses power | WebSocket disconnects, backend detects it |
| Video file ends (if `source` was a file) | `StopIteration` raised, SDK calls `stop()` |

When the ingest WebSocket disconnects, the backend:
1. Marks the session as `completed` in the database
2. Records the final zone coverage
3. Removes the session from in-memory state
4. Dashboard viewers see the feed stop (connection closes)

### Step 5: Review past inspections

After a session completes:

1. Go to **Dashboard → Inspections** to see all past sessions with date, duration,
   coverage, and finding counts.
2. Click any session ID to view its full detail — all findings (color-coded by
   severity), zone coverage percentage, and the generated report.
3. RED findings require immediate attention. YELLOW findings are advisory.

### Putting it all together

```
┌─────────────────────────────────────────────────────────────────────┐
│  DRONE / RPI                                                        │
│                                                                     │
│  1. python inspect.py                                               │
│     └─ cw.connect() ─── POST /api/sessions ──▶ backend creates     │
│     └─ cw.run()     ─── WS /ws/ingest/{id} ──▶ frames flow         │
│                                                                     │
│  4. Ctrl+C or cw.stop()                                             │
│     └─ WS closes    ─── backend marks session "completed"           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                    frames + results flow
                    in real time via Modal
                              │
┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER (operator)                                                 │
│                                                                     │
│  2. Open dashboard_url                                              │
│     └─ WS /ws/view/{id} ──▶ live video + detections + analysis     │
│                                                                     │
│  3. Click mic / report / mode toggle                                │
│     └─ Actions sent through viewer WS, processed against latest    │
│        frame from the drone                                         │
│                                                                     │
│  5. After session ends:                                             │
│     └─ Dashboard → Inspections → click session → full history      │
└─────────────────────────────────────────────────────────────────────┘
```

### Multiple sessions

Each `cw.connect()` call creates a **new, independent session** with its own ID and
dashboard URL. You can run multiple drones simultaneously — each gets its own session,
and an operator can open multiple browser tabs to watch them all. All sessions tied to
the same API key appear under the same user account in the dashboard.

---

## 8. How it works under the hood

### Quality gate

The SDK doesn't send every frame. Before sending, each frame passes through:

- **Blur check** — Laplacian variance must be ≥ 100 (rejects motion blur)
- **Motion check** — Mean pixel difference from previous frame must be ≥ 1.0 (skips static frames)
- **Rate limit** — Minimum 200ms between sends, force-send after 350ms even without motion

This keeps bandwidth low (~3-5 fps of useful frames) while the camera may be running at 30fps.

### Processing pipeline

```
Frame arrives at backend
  ├─ Immediately relayed to all dashboard viewers (no processing delay)
  ├─ YOLO detection (runs on every frame, ~30-60ms on GPU)
  │   └─ Detections sent to SDK + viewers
  └─ Qwen2-VL analysis (runs every ~3s when equipment is in frame)
      └─ Analysis + findings sent to SDK + viewers, persisted to database
```

### Connection architecture

```
SDK on Pi          Modal Backend           Dashboard in Browser
─────────          ─────────────           ────────────────────
POST /api/sessions ──────────▶ Creates session, returns session_id + ws_url
                                     │
WS /ws/ingest/{id} ◀────────────────┘
  auth handshake ──▶ validates API key
  frame messages ──▶ relayed + processed ──▶ WS /ws/view/{id}
  ◀── detections ──                    ──▶ detections
  ◀── analysis ────                    ──▶ analysis
  ◀── findings ────                    ──▶ findings
```

---

## 9. Configuration reference

### SDK defaults

| Parameter | Value | Description |
|-----------|-------|-------------|
| `FRAME_INTERVAL` | 0.2s | Minimum time between frame sends |
| `FORCE_SEND_MS` | 350ms | Force-send even without motion after this |
| `JPEG_QUALITY` | 85 | JPEG encoding quality (10–95) |
| `BLUR_THRESHOLD` | 100.0 | Minimum Laplacian variance to accept a frame |
| `MOTION_THRESHOLD` | 1.0 | Minimum pixel diff to trigger a send |

### Backend server

The default backend URL is `https://gitbolt--dronecat-web.modal.run`. To point the SDK at a different server:

```python
cw = CatWatch(api_key="your_key", server="https://your-modal-deployment.modal.run")
```

---

## 10. Raspberry Pi setup checklist

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install system dependencies
sudo apt install -y python3-pip python3-venv libcap-dev

# 3. Create a virtual environment
python3 -m venv ~/catwatch-env
source ~/catwatch-env/bin/activate

# 4. Install CatWatch SDK
pip install catwatch

# 5. (CSI camera only) Install picamera2
pip install picamera2

# 6. Create your inspection script
cat > inspect.py << 'EOF'
from catwatch import CatWatch

cw = CatWatch(api_key="cw_live_YOUR_KEY")
cw.connect(source=0, mode="cat")

@cw.on_analysis
def on_analysis(msg):
    sev = msg["data"]["severity"]
    desc = msg["data"]["description"]
    print(f"[{sev}] {desc}")

print(f"Dashboard: {cw.dashboard_url}")
cw.run()
EOF

# 7. Run
python inspect.py
```

To run on boot, create a systemd service:

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
sudo systemctl enable catwatch
sudo systemctl start catwatch
```
