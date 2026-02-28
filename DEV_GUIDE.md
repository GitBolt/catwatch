# CatWatch Development Guide

This guide covers how to set up, deploy, and develop the CatWatch platform, which consists of three main components:
1. **Modal Backend:** The GPU-accelerated orchestrator (YOLO, Qwen2-VL).
2. **Next.js Web App:** The dashboard and API for managing keys and viewing sessions.
3. **Python SDK (`catwatch`):** The client library used by the edge devices (drones/cameras).

---

## 🏗️ 1. Modal Backend Development (`/backend`)

The backend runs on Modal and relies on a PostgreSQL database to store sessions, findings, and reports.

### Fixing the `catwatch-db` Secret Error
If you see the error: `Secret 'catwatch-db' not found in environment 'main'`, it means Modal cannot connect to your PostgreSQL database. 

1. Go to the URL provided in your terminal error: https://modal.com/secrets/heyaabis/main/create?secret_name=catwatch-db (or simply navigate to your Modal Dashboard → Secrets → Create New Secret).
2. Choose **Custom**.
3. Name it exactly: `catwatch-db`
4. Add a Key-Value pair:
   - **Key:** `DATABASE_URL`
   - **Value:** Your PostgreSQL connection string (the exact same one you put in `web/.env`).
5. Click **Deploy Secret**.

### Deploying the Backend
Once the secret is created and you have `modal` installed and authenticated (`modal token new`):

```bash
cd backend
python -m venv env
source env/bin/activate
pip install -r requirements.txt

# Deploy to Modal
modal deploy modal_app/orchestrator.py
```

*Note: You can use `modal serve modal_app/orchestrator.py` during active development to automatically hot-reload the backend when you save your python files.*

---

## 💻 2. Web Dashboard Development (`/web`)

The frontend is a Next.js App Router project using Prisma for database interactions and Magic for passwordless authentication.

### Local Setup
```bash
cd web
npm install

# Make sure your .env has DATABASE_URL, NEXT_PUBLIC_MAGIC_PUBLISHABLE_KEY, and MAGIC_SECRET_KEY
cp ../.env.example .env

# Sync your database schema
npx prisma db push
```

### Running Locally
```bash
npm run dev
```
The dashboard will be available at `http://localhost:3000`.

### Modifying the Database Schema
1. Edit `web/prisma/schema.prisma` to adjust your models.
2. Run `npx prisma format` to format the file.
3. Run `npx prisma db push` to push the changes to your remote database (or generate a migration with `npx prisma migrate dev`).
4. Run `npx prisma generate` to update the local TypeScript client.

---

## 🐍 3. Python SDK Development (`/sdk`)

The SDK connects to the deployed Modal backend. It is managed using **Poetry**.

### Local Setup for testing
```bash
cd sdk
poetry install
```

### Making changes and testing locally
If you want to edit the SDK code and immediately test it with a local script, you can install your local version in editable mode in an external virtual environment:
```bash
# In your test project directory:
python -m venv .venv
source .venv/bin/activate
pip install -e /path/to/catwatch/sdk
```

### Publishing a new SDK version to PyPI
When you are ready to release a new version of the `catwatch` pip package to the public:

1. Open `sdk/pyproject.toml`
2. Increment the `version` (e.g., from `"0.1.0"` to `"0.1.1"`)
3. Open `sdk/catwatch/__init__.py` and match the `__version__` string.
4. Build and publish:
```bash
cd sdk
poetry build
poetry publish
```
*(You will need PyPI API credentials configured in Poetry: `poetry config pypi-token.pypi your-token-here`)*

---

## 🧭 Environment Architecture Cheat Sheet

- **SDK (`catwatch.CatWatch`)** sends a `POST /api/sessions` to the **Web App** (using the Modal URL configured in `defaults.py` or overridden at runtime).
- **Web App** creates the session in PostgreSQL and returns the Modal WebSocket ingest URL.
- **SDK** opens a WebSocket connection to `wss://catwatch-hackillinois.vercel.app/ws/ingest/{id}` on the **Modal Backend**.
- **Modal Backend** streams frames, runs YOLO + Qwen, and writes Findings / Reports directly to **PostgreSQL** using the `catwatch-db` secret.
- **Dashboard Viewers** open a WebSocket connection to `wss://catwatch-hackillinois.vercel.app/ws/view/{id}` on the **Modal Backend** to watch the inspection live.
