# CatWatch SDK

AI-powered drone inspection SDK. Connect any camera to the CatWatch platform for real-time YOLO object detection, VLM analysis (Qwen 2.5-VL), fleet memory, and PDF report generation.

## Install

```bash
pip install catwatch
```

**Requirements:** Python 3.9+, OpenCV, NumPy, websockets

For Raspberry Pi camera support:

```bash
pip install catwatch[picamera]
```

## Quick Start

```python
from catwatch import CatWatch

cw = CatWatch("cw_live_YOUR_API_KEY")
cw.connect(source=0, mode="cat", unit_serial="CAT325-001")

@cw.on_analysis
def handle(msg):
    d = msg["data"]
    print(f"[{d['severity']}] {d['description']}")

cw.run()
```

That's it. Open `cw.dashboard_url` in a browser to see the live feed with detections, AI analysis, and zone tracking. GPU inference only starts when a viewer connects.

## API Reference

### `CatWatch(api_key, server=None)`

Create a CatWatch client.

| Param | Type | Description |
|-------|------|-------------|
| `api_key` | `str` | Your API key from the dashboard (starts with `cw_live_`) |
| `server` | `str` | Backend URL. Defaults to the hosted platform. |

---

### `cw.connect(source, mode, unit_serial, model, fleet_tag)`

Create a session and connect to the inspection backend.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `source` | `int \| str \| Picamera2` | `0` | Camera index, video file path, RTSP URL, or Picamera2 object |
| `mode` | `str` | `"general"` | `"general"` for open-ended inspection, `"cat"` for CAT equipment-specific |
| `unit_serial` | `str` | `None` | Equipment serial number — enables fleet memory across inspections |
| `model` | `str` | `None` | Equipment model (e.g. `"CAT 325"`) |
| `fleet_tag` | `str` | `None` | Fleet group identifier for cross-unit pattern matching |

```python
# USB webcam
cw.connect(source=0)

# Video file
cw.connect(source="inspection_footage.mp4")

# RTSP drone feed
cw.connect(source="rtsp://192.168.1.10:8554/stream")

# Raspberry Pi camera
from picamera2 import Picamera2
cam = Picamera2()
cam.start()
cw.connect(source=cam, mode="cat", unit_serial="CAT325-007")
```

---

### `cw.run()`

Start the blocking main loop. Captures frames, applies quality gates, encodes, streams to the backend, and dispatches callbacks.

- Stops on `Ctrl+C`, `cw.stop()`, or when the operator ends the session from the dashboard
- Skips GPU inference until at least one viewer is connected

```python
cw.connect(source=0)
cw.run()  # blocks until stopped
```

---

### `cw.stop()`

Stop the inspection, close the WebSocket, and release the camera.

---

### Context Manager

```python
with CatWatch("cw_live_...") as cw:
    cw.connect(source=0, mode="cat")
    cw.run()
# camera and WebSocket released automatically
```

---

## Properties

Read-only state accessible at any time after `connect()`:

| Property | Type | Description |
|----------|------|-------------|
| `cw.session_id` | `str` | 12-character hex session ID |
| `cw.dashboard_url` | `str` | URL to the live dashboard — share with the operator |
| `cw.connected` | `bool` | `True` if WebSocket is open |
| `cw.mode` | `str` | Current inspection mode (`"general"` or `"cat"`) |
| `cw.zones_seen` | `frozenset` | Zone IDs detected so far |
| `cw.coverage` | `int` | Coverage percentage (0–100) |
| `cw.frame_count` | `int` | Total frames sent to backend |
| `cw.viewers` | `int` | Number of dashboard viewers connected |
| `cw.latest_frame` | `np.ndarray \| None` | Most recent BGR frame from the camera |

---

## Callbacks

Register event handlers using decorators. Each receives a `msg` dict from the server.

### `@cw.on_detection`

Fires on every YOLO detection cycle.

```python
@cw.on_detection
def handle(msg):
    for det in msg["detections"]:
        print(f"{det['label']} ({det['confidence']:.0%}) zone={det['zone']}")
    print(f"Coverage: {msg['coverage']}/15 zones, YOLO took {msg['yolo_ms']}ms")
```

`msg` keys: `detections`, `coverage`, `total_zones`, `yolo_ms`, `frame_id`, `mode`

### `@cw.on_analysis`

Fires when the VLM (Qwen 2.5-VL) analyzes a frame. Runs every ~3 seconds when equipment is in frame.

```python
@cw.on_analysis
def handle(msg):
    d = msg["data"]
    print(f"[{d['severity']}] {d['description']}")
    if d["findings"]:
        print(f"Findings: {d['findings']}")
```

`msg["data"]` keys: `description`, `severity` (`GREEN`/`YELLOW`/`RED`), `findings`, `callout`, `confidence`, `zone`

### `@cw.on_finding`

Fires when a finding is recorded and persisted.

```python
@cw.on_finding
def handle(msg):
    f = msg["data"]
    print(f"[{f['rating']}] Zone {f['zone']}: {f['description']}")
```

`msg["data"]` keys: `zone`, `rating`, `description`, `createdAt`, `snapshot` (base64, for RED/YELLOW only)

### `@cw.on_zone_first_seen`

Fires when a new zone enters the camera frame for the first time.

```python
@cw.on_zone_first_seen
def handle(msg):
    print(f"New zone detected: {msg['zone']}")
```

### `@cw.on_voice_answer`

Fires when the AI responds to a question asked via `cw.ask()`.

```python
@cw.on_voice_answer
def handle(msg):
    print(f"AI says: {msg['text']}")
```

### `@cw.on_report`

Fires when report generation completes (triggered by `cw.generate_report()`).

```python
@cw.on_report
def handle(msg):
    print(f"Report ready: {msg['data']}")
```

### `@cw.on_viewer_joined`

Fires when an operator opens the dashboard. GPU inference begins at this point.

```python
@cw.on_viewer_joined
def handle(msg):
    print(f"{msg['viewers']} viewer(s) connected — inference active")
```

### `@cw.on_mode_change`

Fires when the inspection mode is changed (from dashboard or `cw.set_mode()`).

```python
@cw.on_mode_change
def handle(msg):
    print(f"Mode switched to: {msg['mode']}")
```

### `@cw.on_session_ended`

Fires when the operator ends the session from the dashboard.

```python
@cw.on_session_ended
def handle(msg):
    d = msg["data"]
    print(f"Session over — {d['zones_inspected']} zones, {d['coverage_pct']}% coverage, {d['findings_count']} findings")
```

---

## Actions

### `cw.ask(question)`

Ask the AI a question about what the camera currently sees. The answer arrives via `@cw.on_voice_answer`.

```python
cw.ask("Is there any visible rust on the boom arm?")
```

### `cw.set_mode(mode)`

Switch inspection mode live. Raises `ValueError` if mode is invalid.

```python
cw.set_mode("cat")   # switch to CAT equipment mode
cw.set_mode("general")  # switch back to general
```

### `cw.send_sensor(data)`

Send auxiliary sensor telemetry to enrich the AI analysis.

```python
cw.send_sensor({
    "audio": {"anomaly_score": 0.3},
    "ir": {"anomaly_score": 0.1},
    "light": {"quality": "good"},
})
```

### `cw.generate_report(...)`

Trigger a full inspection report. The result arrives via `@cw.on_report`.

```python
cw.generate_report(
    model="CAT 325",
    serial="CAT325-001",
    technician="John",
    hours=3847,
    duration_minutes=45,
)
```

### `cw.send(payload)`

Send a raw JSON dict through the WebSocket for advanced use cases.

```python
cw.send({"type": "request_vlm_analysis"})
```

---

## Fleet Memory

When you pass `unit_serial` to `connect()`, the platform tracks inspection history for that unit across sessions using [Supermemory](https://supermemory.ai):

```python
cw.connect(source=0, mode="cat", unit_serial="CAT325-001", fleet_tag="fleet_alpha")
```

On subsequent inspections of the same unit:
- The AI sees prior findings and can detect **progression** (e.g. YELLOW → RED)
- Zone briefs include what was found last time
- Fleet-wide patterns are surfaced (e.g. "3 other units had boom seal failures at similar hours")

---

## Frame Pipeline

The SDK handles frame optimization automatically:

| Setting | Default | Description |
|---------|---------|-------------|
| Frame rate | ~15 FPS | Configurable via `FRAME_INTERVAL` |
| JPEG quality | 70 | Lower = smaller frames, faster sends |
| Stream width | 640px | Downscaled before encoding |
| Blur threshold | 100.0 | Frames below this sharpness are skipped |
| Motion threshold | 1.0 | Static frames are skipped (force-sent after 150ms) |

Frames are sent as **binary WebSocket messages** (13-byte header + raw JPEG) with zero base64 overhead.

---

## Full Example

```python
from catwatch import CatWatch

cw = CatWatch("cw_live_YOUR_KEY")
cw.connect(
    source=0,
    mode="cat",
    unit_serial="CAT325-001",
    model="CAT 325",
    fleet_tag="site_alpha",
)

print(f"Dashboard: {cw.dashboard_url}")

@cw.on_detection
def on_det(msg):
    print(f"{len(msg['detections'])} objects | {msg['coverage']}/15 zones")

@cw.on_analysis
def on_analysis(msg):
    d = msg["data"]
    print(f"[{d['severity']}] {d['description']}")

@cw.on_finding
def on_finding(msg):
    f = msg["data"]
    print(f"FINDING [{f['rating']}] {f['zone']}: {f['description']}")

@cw.on_zone_first_seen
def on_zone(msg):
    print(f"New zone: {msg['zone']} ({len(cw.zones_seen)}/15)")

@cw.on_viewer_joined
def on_viewer(msg):
    print(f"Operator connected ({msg['viewers']} viewers)")

@cw.on_session_ended
def on_end(msg):
    d = msg["data"]
    print(f"Done — {d['coverage_pct']}% coverage, {d['findings_count']} findings")

cw.run()
```
