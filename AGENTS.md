# AGENTS.md

## Cursor Cloud specific instructions

### Overview

EIR OCR Platform — a single-product repo (not a monorepo) with a **FastAPI backend** (Python 3.14) and a **Vue 3 / Vite frontend** (Node 22). No database or external queue; the app is stateless.

### Services

| Service | Port | How to start |
|---|---|---|
| FastAPI backend | 8000 | `./dev.sh backend` or `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| Vite dev server | 5173 | `./dev.sh frontend` or `cd frontend && npm run dev -- --host 0.0.0.0` |
| Both together | 8000 + 5173 | `./dev.sh` |

### Development commands

See `README.md` and `./dev.sh` for the full list. Key commands:

- **Setup**: `./dev.sh setup` — creates venv, installs Python + Node deps, copies `.env.example` to `backend/.env`
- **Tests**: `./dev.sh test` or `cd backend && source .venv/bin/activate && pytest -v --tb=short`
- **Backend lint**: `cd backend && .venv/bin/ruff check .`
- **Frontend typecheck**: `cd frontend && npx vue-tsc --noEmit`
- **Frontend lint**: ESLint 9 is installed but no `eslint.config.js` exists yet; `npm run lint` will error until config is added.

### Non-obvious caveats

- **Python 3.14 is mandatory.** The `dev.sh` script hardcodes `python3.14` as the interpreter. The deadsnakes PPA provides it on Ubuntu: `sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get install -y python3.14 python3.14-venv python3.14-dev`.
- **Google Gemini API credentials are required for OCR extraction** (the core feature). Without `GOOGLE_API_KEY` or a GCP service account in `backend/.env`, uploads will return an auth error. Tests mock the API so `pytest` runs without credentials.
- **Credential routing priority in `_build_client()`** (in `vertex_gemini.py`): if `GOOGLE_CLOUD_PROJECT` is set, the code uses Vertex AI + ADC (Application Default Credentials / service account), ignoring `GOOGLE_API_KEY`. To use API-key auth, `GOOGLE_CLOUD_PROJECT` must be empty in `backend/.env`. The `backend/.env` file values override environment variables for pydantic-settings.
- **Odoo credentials are optional** — only needed for the "commit to ERP" step; everything else works without them.
- **`dev.sh` has a `free_port` helper** that kills stale processes on ports 8000/5173 before starting servers. If you start servers manually, be aware of port conflicts.
- **Frontend builds into `backend/static/`** (configured in `vite.config.ts`). In production the FastAPI app serves the SPA; in dev you run separate servers.
