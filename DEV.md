# CatWatch — Developer Guide

Internal reference for deploying, developing, and testing the platform.

---

## Architecture

```
SDK (Python)  ──POST /api/sessions──▶  Modal Backend (GPU)
              ◀══WS /ws/ingest/{id}══▶  Qwen2-VL (A100) + Whisper
                                        FastAPI orchestrator
                                              │
Dashboard (Next.js, Vercel)  ◀══WS /ws/view/{id}══╯
       │
       ├── /api/memory ──▶ Supermemory (inspection knowledge base)
       ├── /api/generate-claim ──▶ OpenAI GPT-4o-mini (insurance claims)
       └── Prisma ORM ──▶ PostgreSQL (Railway)
```

Key behaviors:
- GPU inference only runs when at least one dashboard viewer is connected
- Only one session per user at a time — creating a new session auto-closes any existing one
- Two modes: `"general"` (workplace safety) and `"797"` (CAT 797F defect inspection)
- VLM fires on cadence (~every 3s), not gated on any other condition
- The VLM auto-identifies equipment type and builds a dynamic zone checklist (797 mode)
- Findings mentioning image quality issues (blur, poor lighting, etc.) are hard-filtered before DB write

---

## Repo Structure

- `sdk/catwatch/` — Python SDK (connect, stream, callbacks). Key files: `client.py`, `protocol.py`, `source.py`, `defaults.py`
- `backend/modal_app/` — Modal GPU backend. `orchestrator.py` (FastAPI + WebSocket + insights engine), `yolo_detector.py` (model wrapper, loaded but not in main inference path), `qwen_vl.py` (Qwen2-VL + Whisper), `db.py` (asyncpg helpers)
- `backend/prompts.py` — VLM prompts and zone personas per mode
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

Create the Modal secret (one-time). The backend reads `DATABASE_URL` and `DASHBOARD_URL` from this secret:

```bash
modal secret create catwatch-db \
  DATABASE_URL=postgresql://user:pass@host:5432/db \
  DASHBOARD_URL=https://your-vercel-app.vercel.app
```

### Dashboard (Next.js)

```bash
cd web
yarn install
cp .env.example .env.local
```

Fill in `.env.local` — see `.env.example` for all required variables and explanations.

### SDK (local dev)

```bash
cd sdk && poetry install
```

Or install editable from anywhere: `pip install -e ~/Projects/catwatch/sdk`

---

## Environment Variables

### Web (`web/.env.local`)

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string (same DB as Modal secret) |
| `MAGIC_SECRET_KEY` | ✅ | Magic.link server-side key for validating DID tokens |
| `NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY` | ✅ | Magic.link client-side key (used in login page) |
| `SUPERMEMORY_API_KEY` | ✅ | Supermemory API key for cross-inspection fleet memory |
| `OPENAI_API_KEY` | ✅ | OpenAI key for AI-generated insurance claim documents (`gpt-4o-mini`) |
| `NEXT_PUBLIC_BACKEND_WS` | optional | Override the Modal WebSocket URL (defaults to the hardcoded production URL) |

**Where to get them:**
- `DATABASE_URL` — Railway project → Settings → Environment → DATABASE_URL
- `MAGIC_SECRET_KEY` + `NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY` — dashboard.magic.link → Your App → API Keys
- `SUPERMEMORY_API_KEY` — supermemory.ai → Settings → API Keys
- `OPENAI_API_KEY` — platform.openai.com → API Keys

### Backend (Modal secret `catwatch-db`)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `DASHBOARD_URL` | Base URL of the deployed dashboard (used to build session dashboard links) |

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
poetry version patch   # or minor/major
poetry build && poetry publish
```

Current version: **0.3.x** (breaking change from 0.2.x — `mode="cat"` removed, use `mode="797"`)

---

## Key Backend Concepts

**Session lifecycle**: SDK calls `POST /api/sessions` → backend closes any existing active sessions for this user → creates new session → returns WebSocket URLs. When the SDK disconnects or the operator clicks End, the session is marked completed.

**Qwen-only inference pipeline**: `qwen_vl.py` runs Qwen2-VL on every analysis cadence (~3s). There is no YOLO gate — analysis fires regardless of frame content. The YOLO model file exists in `yolo_detector.py` but is not in the main runtime inference path.

**Two modes**:
- `"general"` (`_MODE_BYTE = 0`) — safety monitoring persona. Flags hazards, PPE, unsafe conditions.
- `"797"` (`_MODE_BYTE = 1`) — CAT 797F inspection persona. Finds defects, wear, leaks, structural damage. Reports "No 797F visible" only when truck is genuinely absent; "Components normal" when truck is visible but no defects found.

**Blur filter**: Before `save_finding()`, a hard keyword filter in `orchestrator.py` drops any finding mentioning image quality (blur, motion blur, poor lighting, overexposed, out of focus, etc.). This prevents Qwen output constraint failures from leaking into the DB.

**Equipment auto-identification**: On session start in 797 mode, `qwen_vl.identify_equipment()` runs once to determine equipment type, model, and inspectable zones. This populates the zone checklist on the dashboard.

**Multi-signal correlation**: After each VLM analysis, `_correlate_signals()` checks if VLM finding keywords match cross-zone patterns (e.g. hydraulic zone findings + coolant zone findings = possible system failure insight). Pure in-memory, no GPU cost.

**Analysis history + severity drift**: Each VLM analysis is stored per-zone (up to 10). `_compute_zone_trend()` derives severity counts, average confidence, and drift direction (worsening/improving/stable/inconsistent).

**Location persistence**: Browser Geolocation API → Nominatim reverse geocoding → direct `PATCH /api/inspections/[id]/location` REST call. This is separate from the WebSocket to avoid timing issues (geo may resolve after WS closes).

**Supermemory integration**: Findings are stored automatically via `/api/memory` using `unit_serial`, `location`, or browser geolocation as the container tag. On session start, the unit/site profile is fetched and injected into the VLM persona prompt.

**Insurance claims**: `POST /api/generate-claim` sends inspection findings to OpenAI GPT-4o-mini, which generates a structured JSON claim document. Requires `OPENAI_API_KEY` in web env.

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
cw.connect(source=0, mode='797', unit_serial='TEST001')
cw.run()
"
```

### Test with temporary Modal deployment

```bash
modal serve -m backend.modal_app.orchestrator
```

Then set `NEXT_PUBLIC_BACKEND_WS` to the ephemeral Modal URL in `.env.local`.

---

## Updating the Backend URL

If the Modal URL changes, update in three places:
1. `sdk/catwatch/defaults.py` → `DEFAULT_SERVER`
2. `web/hooks/use-session-socket.ts` → `BACKEND_WS` fallback
3. Vercel env var → `NEXT_PUBLIC_BACKEND_WS` (then redeploy)

---

## PDF Report

Generated client-side via `jsPDF` + `jsPDF-autotable` in `web/lib/generate-pdf.ts`.

- **Inspection Details** — single-column table: Inspector, Equipment (N/A in general mode), Date, Duration, Location, Status. Serial/Fleet Tag rows only appear when present.
- **Summary Table** — zone × severity × status. "None" components are filtered out.
- **Findings by Zone** — per-zone breakdown with part links to parts.cat.com search.
- **Status column** (not "Code") — GREEN/YELLOW/RED/GRAY with colored chips.

---

## Troubleshooting

- **404 on `/api/sessions`** — backend not deployed. Run `modal deploy -m backend.modal_app.orchestrator`
- **401 on connect** — invalid API key
- **500 on connect** — DB schema mismatch. Run `npx prisma db push`
- **`ValueError: mode must be one of general, 797`** — SDK is v0.2.x. Run `pip install --upgrade catwatch` to get v0.3+
- **No VLM analysis** — no dashboard viewer connected (GPU gating). VLM fires on cadence; wait ~5s after dashboard loads
- **Location not appearing in PDF** — browser geolocation permission denied, or Nominatim reverse-geocoding timed out. Location is persisted via `PATCH /api/inspections/[id]/location` — check browser console for errors
- **"No 797F visible" when truck is in frame** — redeploy backend with latest `backend/prompts.py`. Old persona sometimes used "No 797F visible" as a catch-all; current version only uses it when no truck is present
- **Blur/image quality findings in report** — redeploy backend. Blur filter may not be active in older deployment
- **Python 3.9 errors** — recreate venv with Homebrew Python 3.11+
- **`Secret not found`** — `modal secret create catwatch-db DATABASE_URL=... DASHBOARD_URL=...`
- **Supermemory empty** — check `SUPERMEMORY_API_KEY` in `.env.local`. Also check browser console for `[memory] store error:` warnings
- **Insurance claim button not shown** — only visible for completed sessions with ≥1 finding. Check `OPENAI_API_KEY` is set in Vercel env vars
- **Multiple active sessions** — `create_session` auto-closes previous sessions. If stale DB rows exist, they'll be cleaned up on next session creation
