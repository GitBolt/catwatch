# pi5/relay.py
"""
Railway relay: polls picam /snapshot and forwards frames to Modal WebSocket.

Usage:
    PICAM_URL=https://xxx.trycloudflare.com \
    MODAL_WS_URL=wss://...modal.run/ws \
    python pi5/relay.py

Optional env vars:
    FRAME_INTERVAL   seconds between snapshots (default: 0.2)
    INSPECTION_MODE  general or cat (default: general)
"""

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi5.capture import PicamCapture


def build_frame_message(jpeg: bytes, frame_id: int, mode: str = "general") -> dict:
    return {
        "type": "frame",
        "data": base64.b64encode(jpeg).decode("utf-8"),
        "frame_id": frame_id,
        "client_ts": time.time(),
        "mode": mode,
    }


async def run_relay(picam_url: str, ws_url: str, interval: float, mode: str):
    import websockets

    print(f"[relay] Connecting to picam at {picam_url}")
    cap = PicamCapture(picam_url, interval=interval)
    print(f"[relay] picam OK — connecting to Modal at {ws_url}")

    frame_id = 0
    async with websockets.connect(ws_url) as ws:
        print("[relay] WebSocket connected — streaming frames")
        while True:
            t0 = time.monotonic()
            jpeg = cap.get_frame()
            if jpeg:
                msg = build_frame_message(jpeg, frame_id, mode)
                await ws.send(json.dumps(msg))
                frame_id += 1
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, interval - elapsed))


def main():
    picam_url = os.environ.get("PICAM_URL", "").strip()
    ws_url = os.environ.get("MODAL_WS_URL", "").strip()
    interval = float(os.environ.get("FRAME_INTERVAL", "0.2"))
    mode = os.environ.get("INSPECTION_MODE", "general")

    if not picam_url:
        print("ERROR: PICAM_URL is not set.", file=sys.stderr)
        sys.exit(1)
    if not ws_url:
        print("ERROR: MODAL_WS_URL is not set.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_relay(picam_url, ws_url, interval, mode))


if __name__ == "__main__":
    main()
