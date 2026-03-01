# CatWatch — Developer Guide

Internal reference for deploying, developing, and testing the platform.

---

## Architecture

```
SDK (Python)  ──POST /api/sessions──▶  Modal Backend (GPU)
              ◀══WS /ws/ingest/{id}══▶  YOLO (T4) + Qwen2-VL (A100)
                                        FastAPI orchestrator
                                              │
Dashboard (Next.js, Vercel)  ◀══WS /ws/view/{id}══╯
       │
       ├── /api/memory ──▶ Supermemory (inspection knowledge base)
       └── Prisma ORM ──▶ PostgreSQL (Railway)
```

Key behaviors:
- GPU inference only runs when at least one dashboard viewer is connected
- Only one session per user at a time — creating a new session auto-closes any existing one
- CAT mode uses a fine-tuned YOLO model, general mode uses vanilla YOLOv8
- The VLM auto-identifies equipment type and builds a dynamic zone checklist (CAT mode only)

---

## Repo Structure

- `sdk/catwatch/` — Python SDK (connect, stream, callbacks). Key files: `client.py`, `protocol.py`, `source.py`, `defaults.py`
- `backend/modal_app/` — Modal GPU backend. `orchestrator.py` (FastAPI + WebSocket + insights engine), `yolo_detector.py` (dual YOLO), `qwen_vl.py` (Qwen2-VL + Whisper), `db.py` (asyncpg helpers)
- `backend/prompts.py` — VLM prompts and zone criteria
- `web/` — Next.js 15 dashboard. `app/dashboard/` for auth-protected pages, `app/session/[id]/` for the live viewer, `hooks/use-session-socket.ts` for the WebSocket + Supermemory hook, `components/` for UI, `lib/` for types, auth, PDF gen, Supermemory client

---

## Prerequisites

You need Python 3.11+, Node 18+, Modal CLI (`pip install modal`), and optionally Vercel CLI. Do NOT use macOS system Python 3.9 — Modal breaks on it.

---

## Environment Setup

### Backend (Modal)

```bash
cd ~/Projects/catwatch
python3 -m venv env && source env/bin/activate
pip install modal
```

Create the Modal secret (one-time):

```bash
modal secret create catwatch-db \
  DATABASE_URL=postgresql://user:pass@host:5432/db \
  DASHBOARD_URL=https://catwatch-hackillinois.vercel.app
```

### Dashboard (Next.js)

```bash
cd web
yarn install
cp .env.example .env.local
```

Fill in `.env.local`: `DATABASE_URL`, `MAGIC_SECRET_KEY`, `NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY`, `SUPERMEMORY_API_KEY`.

### SDK (local dev)

```bash
cd sdk && poetry install
```

Or install editable from anywhere: `pip install -e ~/Projects/catwatch/sdk`

---

## Deploying

### Backend

```bash
source env/bin/activate
modal deploy -m backend.modal_app.orchestrator
```

Verify: `curl https://heyaabis--dronecat-web.modal.run/health`

### Database

After changing `web/prisma/schema.prisma`:

```bash
cd web
npx prisma db push
npx prisma generate
```

If the backend uses new columns, also update the raw SQL in `backend/modal_app/db.py`.

### Frontend

```bash
cd web && vercel --prod
```

Or push to the connected git branch.

### SDK (PyPI)

```bash
cd sdk
poetry version patch
poetry build && poetry publish
```

---

## Key Backend Concepts

**Session lifecycle**: SDK calls `POST /api/sessions` → backend closes any existing active sessions for this user → creates new session → returns WebSocket URLs. When the SDK disconnects or the operator clicks End, the session is marked completed.

**Dual YOLO**: `yolo_detector.py` loads both `yolov8n.pt` (general) and `dronecat_yolo_best.pt` (fine-tuned CAT). The `detect(frame, mode)` method picks the right model per call.

**Equipment auto-identification**: On the first frame with YOLO detections (CAT mode), `qwen_vl.identify_equipment()` runs once to determine equipment type, model, and inspectable zones. This replaces the old hardcoded checklist.

**Multi-signal correlation**: After each VLM analysis, `_correlate_signals()` checks if YOLO detection labels match VLM finding keywords (e.g. "hydraulic_hose" + "fluid stain" = `hydraulic_leak` insight). Pure in-memory, no GPU cost.

**Analysis history + severity drift**: Each VLM analysis is stored per-zone (up to 10). `_compute_zone_trend()` derives severity counts, average confidence, and drift direction (worsening/improving/stable/inconsistent).

**Supermemory integration**: Findings are stored automatically via `/api/memory` using `unit_serial`, `location`, or browser geolocation as the container tag. On session start, the unit/site profile is fetched and injected into the VLM persona prompt.

---

## Local Development

### Dashboard

```bash
cd web && yarn dev
```

### Test SDK against production backend

```bash
pip install -e ~/Projects/catwatch/sdk
python3 -c "
from catwatch import CatWatch
cw = CatWatch(api_key='YOUR_KEY')
cw.connect(source=0, mode='cat', unit_serial='TEST001')
cw.run()
"
```

### Test with temporary Modal deployment

```bash
modal serve -m backend.modal_app.orchestrator
```

---

## Updating the Backend URL

If the Modal URL changes, update in three places:
1. `sdk/catwatch/defaults.py` → `DEFAULT_SERVER`
2. `web/hooks/use-session-socket.ts` → `BACKEND_WS` fallback
3. Vercel env var → `NEXT_PUBLIC_BACKEND_WS` (then redeploy)

---

## Troubleshooting

- **404 on `/api/sessions`** — backend not deployed. Run `modal deploy -m backend.modal_app.orchestrator`
- **401 on connect** — invalid API key
- **500 on connect** — DB schema mismatch. Run `npx prisma db push`
- **No VLM analysis** — no dashboard viewer connected (GPU gating), or YOLO hasn't detected anything yet
- **Python 3.9 errors** — recreate venv with Homebrew Python 3.11+
- **`Secret not found`** — `modal secret create catwatch-db DATABASE_URL=... DASHBOARD_URL=...`
- **Supermemory empty** — check `SUPERMEMORY_API_KEY` in `.env.local`. Also check browser console for `[memory] store error:` warnings
- **Multiple active sessions** — should no longer happen. `create_session` auto-closes previous sessions. If stale DB rows exist, they'll be cleaned up on next session creation.
