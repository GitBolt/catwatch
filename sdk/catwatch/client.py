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

    def connect(self, source=0, mode="general"):
        """Create a session and connect to the inspection backend."""
        self._mode = mode

        # POST /api/sessions to create session
        data = json.dumps({"api_key": self._api_key, "mode": mode}).encode()
        req = urllib.request.Request(
            f"{self._server}/api/sessions",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())

        self._session_id = result["session_id"]
        self._dashboard_url = result.get("dashboard_url", "")
        self._ws_url = result["ws_url"]

        # Open video source
        self._source = VideoSource(source)

        # Start WebSocket protocol
        self._protocol = Protocol(self._ws_url, self._api_key)
        self._protocol.start()

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
