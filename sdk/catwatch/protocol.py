import json
import queue
import threading
import time

import websockets.sync.client


class Protocol:
    """WebSocket client running in a daemon thread with auto-reconnect."""

    def __init__(self, ws_url, api_key):
        self._url = ws_url
        self._api_key = api_key
        self._send_q = queue.Queue(maxsize=2)  # drop old frames
        self._recv_q = queue.Queue(maxsize=64)
        self._running = False
        self._connected = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def send(self, payload):
        """Queue a message to send. Drops oldest if queue is full."""
        if self._send_q.full():
            try:
                self._send_q.get_nowait()
            except queue.Empty:
                pass
        self._send_q.put(payload)

    def recv(self):
        """Non-blocking receive. Returns message dict or None."""
        try:
            return self._recv_q.get_nowait()
        except queue.Empty:
            return None

    @property
    def connected(self):
        return self._connected

    def close(self):
        self._running = False

    def _loop(self):
        backoff = 2.0
        while self._running:
            try:
                with websockets.sync.client.connect(
                    self._url,
                    max_size=10 * 1024 * 1024,
                    close_timeout=10,
                ) as ws:
                    # Auth handshake
                    ws.send(json.dumps({"type": "auth", "api_key": self._api_key}))
                    auth_resp = json.loads(ws.recv(timeout=10))
                    if auth_resp.get("type") == "error":
                        raise RuntimeError(f"Auth failed: {auth_resp.get('message')}")

                    self._connected = True
                    backoff = 2.0

                    while self._running:
                        # Send queued messages
                        try:
                            msg = self._send_q.get(timeout=0.01)
                            ws.send(json.dumps(msg))
                        except queue.Empty:
                            pass

                        # Receive messages
                        try:
                            raw = ws.recv(timeout=0.01)
                            parsed = json.loads(raw)
                            if not self._recv_q.full():
                                self._recv_q.put(parsed)
                        except TimeoutError:
                            pass

            except Exception as e:
                self._connected = False
                if self._running:
                    print(f"[catwatch] connection lost: {e}, reconnecting in {backoff:.0f}s...")
                    time.sleep(backoff)
                    backoff = min(backoff * 1.5, 30.0)
