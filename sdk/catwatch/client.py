import json
import struct
import threading
import time

import cv2
import urllib.request

from .defaults import (
    DEFAULT_SERVER,
    FRAME_INTERVAL,
    FORCE_SEND_MS,
    JPEG_QUALITY,
    STREAM_WIDTH,
    BLUR_THRESHOLD,
    MOTION_THRESHOLD,
)
from .quality import blur_score, motion_score
from .source import VideoSource
from .protocol import Protocol

_MODE_BYTE = {"general": 0, "cat": 1}


class CatWatch:
    """CatWatch drone inspection SDK.

    Example::

        cw = CatWatch("cw_live_...")
        cw.connect(source=0, mode="cat", unit_serial="797F-001")

        @cw.on_analysis
        def on_analysis(msg):
            print(msg["data"]["description"])

        @cw.on_zone_first_seen
        def new_zone(msg):
            print(f"New zone: {msg['zone']}")

        cw.run()
    """

    def __init__(self, api_key, server=None):
        self._api_key = api_key
        self._server = (server or DEFAULT_SERVER).rstrip("/")
        self._session_id = None
        self._dashboard_url = None
        self._ws_url = None
        self._source = None
        self._protocol = None
        self._callbacks = {}
        self._running = False
        self._frame_id = 0
        self._prev_gray = None
        self._mode = "general"
        self._zones_seen = set()
        self._coverage = 0
        self._total_zones = 15
        self._viewer_count = 0
        self._latest_frame = None
        self._flip = False
        self._lock = threading.Lock()

    @property
    def dashboard_url(self):
        """URL for the live dashboard view of this session."""
        return self._dashboard_url

    @property
    def session_id(self):
        """Active session ID (12-char hex)."""
        return self._session_id

    @property
    def connected(self):
        """True if the WebSocket to the backend is open."""
        return self._protocol.connected if self._protocol else False

    @property
    def mode(self):
        """Current inspection mode ('general' or 'cat')."""
        return self._mode

    @property
    def zones_seen(self):
        """Set of zone IDs detected so far."""
        return frozenset(self._zones_seen)

    @property
    def coverage(self):
        """Coverage percentage (0-100)."""
        return self._coverage

    @property
    def frame_count(self):
        """Number of frames sent to the backend."""
        return self._frame_id

    @property
    def viewers(self):
        """Number of dashboard viewers currently connected."""
        return self._viewer_count

    @property
    def latest_frame(self):
        """Most recent BGR frame from the camera (numpy array or None)."""
        with self._lock:
            return self._latest_frame

    def connect(self, source=0, mode="general", unit_serial=None, model=None, fleet_tag=None, location=None):
        """Create a session and connect to the inspection backend.

        Args:
            source: Camera index (int), video file path (str), RTSP URL (str),
                    or a Picamera2 object.
            mode: Inspection mode — 'general' or 'cat'.
            unit_serial: Equipment serial number for fleet tracking.
            model: Equipment model (e.g. 'CAT 797F').
            fleet_tag: Fleet group identifier.
            location: Site/location identifier for general mode memory
                      (e.g. 'warehouse-7B', 'site-14', or 'geo:37.77,-122.42').
        """
        self._mode = mode

        body = {"api_key": self._api_key, "mode": mode}
        if unit_serial:
            body["unit_serial"] = unit_serial
        if model:
            body["model"] = model
        if fleet_tag:
            body["fleet_tag"] = fleet_tag
        if location:
            body["location"] = location
        data = json.dumps(body).encode()
        url = f"{self._server}/api/sessions"
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()
            except Exception:
                pass
            if e.code == 401:
                raise RuntimeError(
                    "Invalid API key. Create one at your dashboard (API Keys page)."
                ) from None
            elif e.code == 404:
                raise RuntimeError(
                    f"Backend not reachable at {self._server} (404). "
                    f"Is it deployed? Try: curl {self._server}/health"
                ) from None
            else:
                raise RuntimeError(
                    f"Backend error {e.code}: {body or e.reason}"
                ) from None
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Cannot reach backend at {self._server} — {e.reason}. "
                f"Check your internet connection and server URL."
            ) from None

        self._session_id = result["session_id"]
        self._dashboard_url = result.get("dashboard_url", "")
        self._ws_url = result["ws_url"]

        self._source = VideoSource(source)

        self._protocol = Protocol(self._ws_url, self._api_key)
        self._protocol.start()

        print(f"[catwatch] Session created: {self._session_id}")
        print(f"[catwatch] Dashboard: {self._dashboard_url}")
        print(f"[catwatch] Waiting for operator to open dashboard — no GPU usage until then")

    def on_detection(self, fn):
        """Called with YOLO detection results.

        ``msg`` keys: ``detections``, ``coverage``, ``yolo_ms``, ``frame_id``
        """
        self._callbacks["detection"] = fn
        return fn

    def on_analysis(self, fn):
        """Called with VLM analysis results.

        ``msg['data']`` keys: ``description``, ``severity``, ``findings``,
        ``callout``, ``confidence``, ``zone``
        """
        self._callbacks["analysis"] = fn
        return fn

    def on_finding(self, fn):
        """Called when a finding is recorded."""
        self._callbacks["finding"] = fn
        return fn

    def on_voice_answer(self, fn):
        """Called when the AI answers a voice question."""
        self._callbacks["voice_answer"] = fn
        return fn

    def on_report(self, fn):
        """Called when a report is generated."""
        self._callbacks["report"] = fn
        return fn

    def on_zone_first_seen(self, fn):
        """Called when a new zone is detected for the first time.

        ``msg`` keys: ``zone`` (zone ID string)
        """
        self._callbacks["zone_first_seen"] = fn
        return fn

    def on_viewer_joined(self, fn):
        """Called when an operator opens the dashboard.

        ``msg`` keys: ``viewers`` (int count)
        """
        self._callbacks["viewer_joined"] = fn
        return fn

    def on_mode_change(self, fn):
        """Called when the inspection mode changes.

        ``msg`` keys: ``mode`` ('general' or 'cat')
        """
        self._callbacks["mode"] = fn
        return fn

    def on_session_ended(self, fn):
        """Called when the session is ended from the dashboard.

        ``msg['data']`` keys: ``zones_inspected``, ``coverage_pct``, ``findings_count``
        """
        self._callbacks["session_ended"] = fn
        return fn

    def send(self, payload):
        """Send a raw JSON message through the WebSocket."""
        if self._protocol:
            self._protocol.send(payload)

    def ask(self, question):
        """Ask the AI a question about what the camera sees.

        The answer arrives via the ``on_voice_answer`` callback.
        """
        self.send({"type": "voice_question", "text": question})

    def set_mode(self, mode):
        """Switch inspection mode ('general' or 'cat')."""
        if mode not in ("general", "cat"):
            raise ValueError("mode must be 'general' or 'cat'")
        self._mode = mode
        self.send({"type": "set_mode", "mode": mode})

    def flip_camera(self, enabled=True):
        """Rotate the camera feed 180 degrees.

        Args:
            enabled: True to flip, False to reset to normal orientation.
        """
        self._flip = enabled

    def send_sensor(self, data):
        """Send sensor telemetry (audio, IR, etc.) to the backend.

        Args:
            data: Dict with sensor readings, e.g.
                  ``{"audio": {"anomaly_score": 0.3}, "ir": {"anomaly_score": 0.1}}``
        """
        self.send({"type": "sensor", "data": data})

    def generate_report(self, model="CAT 797F", serial="", technician="",
                        hours=0, duration_minutes=0):
        """Trigger report generation on the backend.

        The report arrives via the ``on_report`` callback.
        """
        self.send({
            "type": "generate_report",
            "model": model,
            "serial": serial,
            "technician": technician,
            "hours": hours,
            "duration_minutes": duration_minutes,
            "coverage_percent": self._coverage,
        })

    def _encode_frame(self, frame):
        """Downscale, JPEG-encode, and pack into binary frame message."""
        if self._flip:
            frame = cv2.flip(frame, -1)
        h, w = frame.shape[:2]
        if w > STREAM_WIDTH:
            scale = STREAM_WIDTH / w
            frame = cv2.resize(
                frame,
                (STREAM_WIDTH, int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        jpeg_bytes = buf.tobytes()

        self._frame_id += 1
        header = struct.pack(
            "!IdB",
            self._frame_id,
            time.time(),
            _MODE_BYTE.get(self._mode, 0),
        )
        return header + jpeg_bytes

    def _dispatch(self, msg):
        """Route a server message to the right callback + update internal state."""
        msg_type = msg.get("type")

        if msg_type == "viewer_joined":
            self._viewer_count = msg.get("viewers", 1)
            print(f"[catwatch] Operator connected — inspection active (GPU inference started)")
        elif msg_type == "auth_ok":
            pass
        elif msg_type == "detection":
            self._coverage = msg.get("coverage", self._coverage)
        elif msg_type == "zone_first_seen":
            self._zones_seen.add(msg.get("zone", ""))
        elif msg_type == "mode":
            self._mode = msg.get("mode", self._mode)
        elif msg_type == "session_ended":
            print(f"[catwatch] Session ended by operator")
            self._running = False

        cb = self._callbacks.get(msg_type)
        if cb:
            try:
                cb(msg)
            except Exception as e:
                print(f"[catwatch] callback error ({msg_type}): {e}")

    def run(self):
        """Blocking main loop: capture -> quality gate -> encode -> send -> dispatch callbacks.

        Press Ctrl+C to stop. Can also be stopped by calling ``stop()`` from
        another thread or when the operator ends the session from the dashboard.
        """
        self._running = True
        last_send = 0.0

        try:
            while self._running:
                try:
                    frame, gray = self._source.read()
                except StopIteration:
                    break

                with self._lock:
                    self._latest_frame = frame

                now = time.time()
                elapsed_ms = (now - last_send) * 1000

                blur = blur_score(gray)
                mot = motion_score(self._prev_gray, gray)
                self._prev_gray = gray

                should_send = (
                    (now - last_send) >= FRAME_INTERVAL
                    and (blur >= BLUR_THRESHOLD)
                    and (mot >= MOTION_THRESHOLD or elapsed_ms >= FORCE_SEND_MS)
                )

                if should_send:
                    binary_msg = self._encode_frame(frame)
                    self._protocol.send_binary(binary_msg)
                    last_send = now

                while True:
                    msg = self._protocol.recv()
                    if msg is None:
                        break
                    self._dispatch(msg)

                time.sleep(0.005)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Stop the inspection and release resources."""
        self._running = False
        if self._protocol:
            self._protocol.close()
        if self._source:
            self._source.release()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()
