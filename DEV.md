# CatWatch — Developer Guide

Internal reference for deploying, updating, and testing the platform.

---

## Architecture

```
┌──────────────┐     POST /api/sessions      ┌─────────────────────────┐
│  SDK (Python) │ ──────────────────────────▶ │  Modal Backend (GPU)     │
│  pip install   │     WS /ws/ingest/{id}      │  YOLO (T4) + Qwen (A100)│
│  catwatch      │ ◀════════════════════════▶ │  FastAPI orchestrator    │
└──────────────┘                              └────────────┬────────────┘
                                                           │ WS /ws/view/{id}
┌──────────────┐                              ┌────────────▼────────────┐
│  Supermemory  │ ◀──── /api/memory ────────  │  Next.js Dashboard      │
│  (memory API) │                              │  Vercel                  │
└──────────────┘                              └─────────────────────────┘
                                                           │
                                              ┌────────────▼────────────┐
                                              │  PostgreSQL (Railway)    │
                                              │  Prisma ORM              │
                                              └─────────────────────────┘
```

**GPU gating:** YOLO/Qwen only run when at least one viewer is connected to the
dashboard. SDK streams frames immediately but no GPU cost until an operator opens
the session URL.

---

## Repo Structure

```
catwatch/
├── sdk/                        # Python SDK (Poetry package)
│   ├── catwatch/
│   │   ├── client.py           # CatWatch class — connect, run, callbacks
│   │   ├── protocol.py         # WebSocket client with auth + reconnect
│   │   ├── source.py           # Video source abstraction (cam, RTSP, picamera2)
│   │   ├── quality.py          # Blur + motion scoring
│   │   └── defaults.py         # Default server URL, frame intervals
│   └── pyproject.toml          # Poetry config
├── backend/
│   ├── modal_app/
│   │   ├── __init__.py         # Modal app + image definitions
│   │   ├── orchestrator.py     # FastAPI: REST + WebSocket endpoints
│   │   ├── yolo_detector.py    # YOLO inference (T4 GPU)
│   │   ├── qwen_vl.py          # Qwen2-VL inference (A100 GPU)
│   │   └── db.py               # asyncpg helpers (sessions, findings, reports)
│   ├── prompts.py              # VLM prompts, zone inspection criteria
│   └── zone_config.py          # Zone mapping (YOLO label → inspection zone)
├── web/                        # Next.js 15 dashboard
│   ├── app/
│   │   ├── dashboard/          # Auth-protected pages (inspections, keys)
│   │   ├── session/[id]/       # Live inspection viewer
│   │   └── api/                # API routes (auth, keys, memory)
│   ├── hooks/
│   │   └── use-session-socket.ts  # WebSocket hook (+ Supermemory integration)
│   ├── components/             # UI components
│   ├── lib/
│   │   ├── supermemory.ts      # Supermemory API client
│   │   ├── auth.ts             # Magic Link auth
│   │   ├── db.ts               # Prisma client singleton
│   │   ├── types.ts            # WebSocket message types
│   │   └── constants.ts        # Zones, severity colors
│   └── prisma/schema.prisma    # Database schema
├── data/                       # Spec KB, sub-section prompts, CATrack data
├── GUIDE.md                    # Consumer SDK guide
└── DEV.md                      # This file
```

---

## Prerequisites

| Tool | Install | Version check |
|------|---------|--------------|
| Python 3.11+ | `brew install python` | `python3 --version` |
| Node 18+ | `brew install node` | `node --version` |
| Poetry | `pip install poetry` | `poetry --version` |
| Modal CLI | `pip install modal` | `modal --version` |
| Vercel CLI | `npm i -g vercel` | `vercel --version` |

**Important:** Do NOT use the system Python 3.9 from CommandLineTools. Modal's
async internals break on 3.9. Always use Homebrew Python (`/opt/homebrew/bin/python3`).

---

## Environment Setup

### 1. Root venv (for Modal CLI + backend deploys)

```bash
cd ~/Projects/catwatch
python3 -m venv env
source env/bin/activate
pip install modal
```

### 2. Web dashboard

```bash
cd web
npm install
cp .env.example .env.local
# Fill in: DATABASE_URL, MAGIC_SECRET_KEY, NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY, SUPERMEMORY_API_KEY
```

### 3. SDK local dev

```bash
cd sdk
poetry install
```

---

## Secrets & Environment Variables

### Modal secrets

The backend reads secrets at runtime from Modal, not from `.env` files.

```bash
# Create (one-time)
modal secret create catwatch-db DATABASE_URL=postgresql://user:pass@host:5432/db DASHBOARD_URL=https://catwatch.vercel.app

# Update
modal secret create --force catwatch-db DATABASE_URL=postgresql://... DASHBOARD_URL=https://...
```

### Vercel env vars

Set in Vercel dashboard (Settings > Environment Variables) or `.env.local` for local dev:

| Variable | Required | Example |
|----------|----------|---------|
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:5432/railway` |
| `MAGIC_SECRET_KEY` | Yes | `sk_live_...` |
| `NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY` | Yes | `pk_live_...` |
| `SUPERMEMORY_API_KEY` | Yes | `sm_...` |
| `NEXT_PUBLIC_BACKEND_WS` | No | `wss://heyaabis--dronecat-web.modal.run` (default) |

**Note:** `NEXT_PUBLIC_*` vars are baked in at build time. After changing them,
you must redeploy (`vercel --prod`).

---

## Deploying

### Backend (Modal)

```bash
source env/bin/activate
modal deploy -m backend.modal_app.orchestrator
```

This deploys the FastAPI orchestrator + YOLO + Qwen functions. Output shows the URL:

```
✓ Created web function web => https://heyaabis--dronecat-web.modal.run
```

**Verify:**

```bash
curl https://heyaabis--dronecat-web.modal.run/health
# → {"status":"ok","service":"dronecat","sessions":0}
```

**Common issues:**

| Error | Fix |
|-------|-----|
| `Secret 'catwatch-db' not found` | `modal secret create catwatch-db DATABASE_URL=... DASHBOARD_URL=...` |
| `No module named 'backend/modal_app'` | Use `-m` flag: `modal deploy -m backend.modal_app.orchestrator` |
| `CancelledError` spam | You're on Python 3.9. Recreate venv with `python3` (3.11+) |
| `Created objects` but no functions | You deployed `__init__.py` not the orchestrator. Use `backend.modal_app.orchestrator` |

### Database (Prisma)

After changing `web/prisma/schema.prisma`:

```bash
cd web
npx prisma db push      # applies schema changes to Railway
npx prisma generate     # regenerates TypeScript types
```

### Frontend (Vercel)

```bash
cd web
vercel --prod
```

Or push to the connected git branch for auto-deploy.

### SDK (PyPI)

After changing SDK code:

```bash
cd sdk

# Bump version
poetry version patch    # 0.1.0 → 0.1.1
# or: poetry version minor  (0.1.0 → 0.2.0)
# or: poetry version major  (0.1.0 → 1.0.0)

# Build
poetry build

# Publish (first time: poetry config pypi-token.pypi pypi-YOUR_TOKEN)
poetry publish
```

Get a PyPI API token at https://pypi.org/manage/account/token/

For local testing without publishing, install editable from anywhere:

```bash
pip install -e ~/Projects/catwatch/sdk
```

---

## Local Development

### Run dashboard locally

```bash
cd web
npm run dev    # http://localhost:3000
```

### Test SDK against production backend

```bash
cd ~/some-test-dir
python3 -m venv env && source env/bin/activate
pip install -e ~/Projects/catwatch/sdk

python3 -c "
from catwatch import CatWatch
cw = CatWatch(api_key='YOUR_KEY')
cw.connect(source=0, mode='cat', unit_serial='TEST001')
cw.run()
"
```

### Test SDK against local backend (rare)

Modal functions run remotely even during dev. For full local testing, use
`modal serve -m backend.modal_app.orchestrator` which creates a temporary deployment.

---

## E2E Testing: Supermemory Integration

### First inspection (builds memory)

```python
from catwatch import CatWatch

cw = CatWatch(api_key="YOUR_KEY")
cw.connect(source=0, mode="cat", unit_serial="TEST001", fleet_tag="fleet_alpha")
cw.run()
# Open dashboard URL → Unit Memory panel shows "No prior history"
# Point webcam at CAT equipment → findings flow
# Ctrl+C to stop
```

### Verify storage

```bash
curl -s "https://catwatch.vercel.app/api/memory?action=profile&unitSerial=TEST001" | python3 -m json.tool
```

### Second inspection (memory kicks in)

Run the same script again. Unit Memory panel now shows prior findings.
VLM analysis references past context in its assessments.

### Fleet intelligence

Run a second unit (`unit_serial="TEST002"`, same `fleet_tag`). Then view either
inspection in Dashboard > Inspections — "Similar Findings Across Fleet" section
shows semantically matched cross-unit findings.

### Verification checklist

| # | Check | How to verify |
|---|-------|--------------|
| 1 | Backend health | `curl .../health` → `{"status":"ok"}` |
| 2 | SDK connects | Console prints session_id + dashboard_url |
| 3 | GPU gating | No YOLO/analysis until dashboard is opened |
| 4 | `viewer_joined` | Console prints "Operator connected" when dashboard opens |
| 5 | Detections flow | `[YOLO] N detections` in console |
| 6 | VLM analysis | `[VLM] [GREEN/YELLOW/RED]` in console |
| 7 | Unit Memory panel | Shows serial, model, fleet in dashboard sidebar |
| 8 | Supermemory stores | Profile endpoint returns findings after inspection |
| 9 | Memory recall | Second inspection shows prior history + VLM uses context |
| 10 | Fleet search | Inspection detail shows cross-unit similar findings |

---

## Updating the Backend URL

The Modal URL contains your workspace name. If it changes, update in **three places**:

1. `sdk/catwatch/defaults.py` → `DEFAULT_SERVER`
2. `web/hooks/use-session-socket.ts` → `BACKEND_WS` fallback
3. Vercel env var → `NEXT_PUBLIC_BACKEND_WS` (then redeploy)

Current URL: `https://heyaabis--dronecat-web.modal.run`

---

## Database Schema Changes

1. Edit `web/prisma/schema.prisma`
2. `cd web && npx prisma db push` (applies to Railway)
3. `npx prisma generate` (updates TypeScript types)
4. If backend uses the new columns: update `backend/modal_app/db.py` SQL queries
5. Redeploy backend: `modal deploy -m backend.modal_app.orchestrator`

The backend uses raw SQL via asyncpg (not Prisma) — column names must match
the Prisma schema exactly (camelCase with quotes: `"unitSerial"`).

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| 404 on `/api/sessions` | Backend not deployed. `modal deploy -m backend.modal_app.orchestrator` |
| 401 on connect | Invalid API key. Create one in Dashboard > API Keys |
| 500 on connect | DB schema mismatch. Run `cd web && npx prisma db push` |
| Dashboard WS fails | Wrong `NEXT_PUBLIC_BACKEND_WS`. Update in Vercel + redeploy |
| No VLM analysis | No viewers connected (GPU gating). Open the dashboard URL first |
| Python 3.9 errors | Recreate venv: `python3 -m venv env` (use Homebrew Python 3.11+) |
| `Secret not found` | `modal secret create catwatch-db DATABASE_URL=... DASHBOARD_URL=...` |
| Supermemory empty | Check `SUPERMEMORY_API_KEY` in Vercel. Dashboard must be open during inspection |
| SDK changes not picked up | `pip install -e ./sdk` for editable install, or bump + `poetry publish` |
