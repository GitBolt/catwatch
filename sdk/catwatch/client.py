import base64
import json
import time

import cv2
import urllib.request

from .defaults import (
    DEFAULT_SERVER,
    FRAME_INTERVAL,
    FORCE_SEND_MS,
    JPEG_QUALITY,
    BLUR_THRESHOLD,
    MOTION_THRESHOLD,
)
from .quality import blur_score, motion_score
from .source import VideoSource
from .protocol import Protocol


class CatWatch:
    """CatWatch drone inspection SDK."""

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

    @property
    def dashboard_url(self):
        return self._dashboard_url

    @property
    def session_id(self):
        return self._session_id

    @property
    def connected(self):
        return self._protocol.connected if self._protocol else False

    def connect(self, source=0, mode="general", unit_serial=None, model=None, fleet_tag=None):
        """Create a session and connect to the inspection backend."""
        self._mode = mode

        # POST /api/sessions to create session
        body = {"api_key": self._api_key, "mode": mode}
        if unit_serial:
            body["unit_serial"] = unit_serial
        if model:
            body["model"] = model
        if fleet_tag:
            body["fleet_tag"] = fleet_tag
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
                    f"Invalid API key. Create one at your dashboard (API Keys page)."
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

        # Open video source
        self._source = VideoSource(source)

        # Start WebSocket protocol
        self._protocol = Protocol(self._ws_url, self._api_key)
        self._protocol.start()

        print(f"[catwatch] Session created: {self._session_id}")
        print(f"[catwatch] Dashboard: {self._dashboard_url}")
        print(f"[catwatch] Waiting for operator to open dashboard — no GPU usage until then")

    def on_detection(self, fn):
        """Decorator: called with detection message dict."""
        self._callbacks["detection"] = fn
        return fn

    def on_analysis(self, fn):
        """Decorator: called with analysis message dict."""
        self._callbacks["analysis"] = fn
        return fn

    def on_finding(self, fn):
        """Decorator: called with finding message dict."""
        self._callbacks["finding"] = fn
        return fn

    def on_voice_answer(self, fn):
        """Decorator: called with voice_answer message dict."""
        self._callbacks["voice_answer"] = fn
        return fn

    def on_report(self, fn):
        """Decorator: called with report message dict."""
        self._callbacks["report"] = fn
        return fn

    def send(self, payload):
        """Send an action through the WebSocket (e.g., voice_question, generate_report)."""
        if self._protocol:
            self._protocol.send(payload)

    def run(self):
        """Blocking main loop: capture -> quality gate -> encode -> send -> dispatch callbacks."""
        self._running = True
        last_send = 0.0

        try:
            while self._running:
                try:
                    frame, gray = self._source.read()
                except StopIteration:
                    break

                now = time.time()
                elapsed_ms = (now - last_send) * 1000

                # Quality gate
                blur = blur_score(frame)
                mot = motion_score(self._prev_gray, gray)
                self._prev_gray = gray

                should_send = (
                    (now - last_send) >= FRAME_INTERVAL
                    and (blur >= BLUR_THRESHOLD)
                    and (mot >= MOTION_THRESHOLD or elapsed_ms >= FORCE_SEND_MS)
                )

                if should_send:
                    _, buf = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                    )
                    b64 = base64.b64encode(buf).decode("ascii")
                    self._frame_id += 1
                    self._protocol.send(
                        {
                            "type": "frame",
                            "data": b64,
                            "frame_id": self._frame_id,
                            "client_ts": now,
                            "mode": self._mode,
                        }
                    )
                    last_send = now

                # Drain received messages and dispatch callbacks
                while True:
                    msg = self._protocol.recv()
                    if msg is None:
                        break
                    msg_type = msg.get("type")

                    # Built-in status messages
                    if msg_type == "viewer_joined":
                        print(f"[catwatch] Operator connected — inspection active (GPU inference started)")
                    elif msg_type == "auth_ok":
                        pass  # already printed on connect

                    cb = self._callbacks.get(msg_type)
                    if cb:
                        try:
                            cb(msg)
                        except Exception as e:
                            print(f"[catwatch] callback error ({msg_type}): {e}")

                # Small sleep to avoid busy-waiting
                time.sleep(0.01)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Clean up resources."""
        self._running = False
        if self._protocol:
            self._protocol.close()
        if self._source:
            self._source.release()
