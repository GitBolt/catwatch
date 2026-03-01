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
        self._send_q = queue.Queue(maxsize=4)
        self._recv_q = queue.Queue(maxsize=64)
        self._running = False
        self._connected = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def send(self, payload):
        """Queue a JSON text message. Drops oldest if queue is full."""
        self._enqueue(json.dumps(payload))

    def send_binary(self, data: bytes):
        """Queue a binary message (e.g. frame header + JPEG). Drops oldest if full."""
        self._enqueue(data)

    def _enqueue(self, item):
        if self._send_q.full():
            try:
                self._send_q.get_nowait()
            except queue.Empty:
                pass
        self._send_q.put(item)

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
                    ws.send(json.dumps({"type": "auth", "api_key": self._api_key}))
                    auth_resp = json.loads(ws.recv(timeout=10))
                    if auth_resp.get("type") == "error":
                        raise RuntimeError(f"Auth failed: {auth_resp.get('message')}")

                    self._connected = True
                    backoff = 2.0

                    while self._running:
                        try:
                            msg = self._send_q.get(timeout=0.005)
                            ws.send(msg)
                        except queue.Empty:
                            pass

                        try:
                            raw = ws.recv(timeout=0.005)
                            if isinstance(raw, str):
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
