# Picam Integration Design

**Date:** 2026-02-28
**Branch:** picam-integration
**Status:** Approved

## Summary

Integrate the [picam](https://github.com/feeniks01/picam) Raspberry Pi camera server into the dronecat inspection pipeline. The Pi runs picam exposed via a cloudflare/ngrok tunnel. The browser polls the tunnel's `/snapshot` endpoint directly for frames, encodes them as base64, and sends them to the Modal orchestrator WebSocket — the same protocol used today by `e2e_webcam_demo.py`. Railway hosts the backend API (reports, inspection records) and is not involved in the camera relay.

## Architecture

```
Raspberry Pi                                         Modal (GPU)
┌─────────────────┐                                ┌──────────────┐
│ picam :8080     │◀── GET /snapshot ──┐           │ orchestrator │
│ + cloudflared   │    (browser polls) │           │  /ws         │
└─────────────────┘                   │      ┌───▶│  YOLO+VLM    │
                                      │      │    └──────────────┘
                               ┌──────┴──────┴─┐
                               │   Browser      │
                               │  Web Frontend  │
                               └──────┬─────────┘
                                      │ REST API calls
                               ┌──────▼─────────┐
                               │    Railway      │
                               │   Backend API   │
                               │ (reports, users,│
                               │  inspection log)│
                               └────────────────┘
```

## Data Flow

1. Browser calls `GET https://<tunnel>/snapshot` at 5fps (200ms interval)
2. Receives raw JPEG bytes → encodes as base64
3. Sends `{"type": "frame", "data": "<b64>", "frame_id": N, "client_ts": T, "mode": "cat"}` to Modal WebSocket
4. Modal orchestrator runs YOLO → VLM → sends `detection` and `analysis` messages back
5. Browser renders overlays and analysis results
6. Browser calls Railway REST API to save findings, generate reports

## Components Delivered in This Branch

### `pi5/capture.py`

`PicamCapture` class — polls `GET /snapshot`, returns raw JPEG bytes.

```python
PicamCapture(url: str, interval: float = 0.2)
    .get_frame() -> bytes | None
    .health_check() -> bool
```

- Connection health check on init with clear error if Pi unreachable
- Respects `FRAME_INTERVAL` — same default (0.2s / 5fps) as the webcam demo
- Thread-safe

### `pi5/relay.py`

Optional fallback Railway relay for environments where the browser cannot reach the picam tunnel directly. Polls picam and forwards frames to Modal WebSocket.

Environment variables:
- `PICAM_URL` — cloudflare/ngrok tunnel URL (required)
- `MODAL_WS_URL` — Modal orchestrator WebSocket URL (required)
- `FRAME_INTERVAL` — seconds between snapshots (default: `0.2`)

### `pi5/requirements.txt`

```
requests
websockets
```

### `.env.example`

Add:
```
# PICAM_URL=https://xxx.trycloudflare.com
```

## Out of Scope (belongs in frontend repo/branch)

- JavaScript fetch loop for browser-side picam polling
- Frontend WebSocket client connecting to Modal
- Railway API endpoints

## Pi Setup (not in this repo)

1. Run picam: `uvicorn server:app --host 0.0.0.0 --port 8080`
2. Expose via tunnel: `cloudflared tunnel --url http://localhost:8080`
3. Set `PICAM_URL` in Railway and frontend env to the tunnel URL

## Environment Variables

| Variable | Where | Description |
|---|---|---|
| `PICAM_URL` | Railway / local | Cloudflare tunnel URL for picam |
| `MODAL_WS_URL` | Railway / browser | Modal orchestrator WebSocket URL |
| `FRAME_INTERVAL` | relay only | Seconds between snapshots (default 0.2) |
