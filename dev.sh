#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev.sh  –  Start the EIR OCR Platform in development mode
#
# Usage:
#   ./dev.sh            # start both backend and frontend
#   ./dev.sh backend    # start only the FastAPI backend
#   ./dev.sh frontend   # start only the Vue/Vite frontend
#   ./dev.sh setup      # first-time setup (venv + npm install)
#   ./dev.sh test       # run backend pytest suite
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
ENV_FILE="$BACKEND/.env"

# ── Colours ───────────────────────────────────────────────────────────────────
# Use $'...' (ANSI-C quoting) so \033 is the actual ESC byte, not literal text.
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m'
MAGENTA=$'\033[0;35m'
BOLD=$'\033[1m'
RESET=$'\033[0m'
DIM=$'\033[2m'

log()  { echo -e "${CYAN}${BOLD}[dev]${RESET} $*"; }
ok()   { echo -e "${GREEN}${BOLD}[dev]${RESET} $*"; }
warn() { echo -e "${YELLOW}${BOLD}[dev]${RESET} $*"; }
err()  { echo -e "${RED}${BOLD}[dev]${RESET} $*" >&2; }

# Prefix every stdin line with a coloured tag (line-buffered via sed -u)
prefix_be()  { sed -u "s/^/${CYAN}[backend] ${RESET}/"; }
prefix_fe()  { sed -u "s/^/${GREEN}[frontend]${RESET} /"; }

# ── Dependency checks ─────────────────────────────────────────────────────────
PYTHON=python3.14

require() {
  if ! command -v "$1" &>/dev/null; then
    if [[ "$1" == "python3.14" ]]; then
      err "Python 3.14 not found. Install it with:"
      err "  sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.14 python3.14-venv"
      err "  brew install python@3.14                     # macOS"
      err "  https://www.python.org/downloads/            # manual"
    else
      err "Required tool not found: $1. Please install it and re-run."
    fi
    exit 1
  fi
}

# ── First-time setup ──────────────────────────────────────────────────────────
setup() {
  require python3.14
  require node
  require npm

  log "Setting up backend Python virtual environment…"
  if [[ ! -d "$VENV" ]]; then
    python3.14 -m venv "$VENV"
    ok "Created venv at $VENV"
  else
    ok "Venv already exists – skipping creation"
  fi

  log "Installing backend dependencies…"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$BACKEND/requirements-dev.txt"
  ok "Backend dependencies installed"

  log "Installing frontend dependencies…"
  (cd "$FRONTEND" && npm install --silent)
  ok "Frontend dependencies installed"

  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ROOT/.env.example" "$ENV_FILE"
    warn ".env created at $ENV_FILE"
    warn "→ Edit it with your GOOGLE_API_KEY and ODOO_* credentials before starting."
  else
    ok ".env already exists – skipping copy"
  fi

  ok "Setup complete. Run  ./dev.sh  to start."
}

# ── Backend ───────────────────────────────────────────────────────────────────
start_backend() {
  require python3.14

  if [[ ! -d "$VENV" ]]; then
    warn "Venv not found. Running setup first…"
    setup
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found – copying from .env.example. Fill in your credentials."
    cp "$ROOT/.env.example" "$ENV_FILE"
  fi

  log "Starting FastAPI backend on ${BOLD}http://localhost:8000${RESET}"
  log "  API docs  → ${BOLD}http://localhost:8000/api/docs${RESET}"

  cd "$BACKEND"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  # PYTHONUNBUFFERED=1 ensures logs flush immediately instead of buffering
  PYTHONUNBUFFERED=1 exec uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    --access-log
}

# ── Frontend ──────────────────────────────────────────────────────────────────
start_frontend() {
  require node
  require npm

  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    warn "node_modules not found. Running npm install…"
    (cd "$FRONTEND" && npm install --silent)
  fi

  log "Starting Vite dev server on ${BOLD}http://localhost:5173${RESET}"
  log "  API proxy → http://localhost:8000"

  cd "$FRONTEND"
  exec npm run dev
}

# ── Both (default) ────────────────────────────────────────────────────────────
start_both() {
  require python3.14
  require node
  require npm

  if [[ ! -d "$VENV" ]] || [[ ! -d "$FRONTEND/node_modules" ]]; then
    warn "Dependencies not installed. Running setup first…"
    setup
  fi

  if [[ ! -f "$ENV_FILE" ]]; then
    warn ".env not found – copying from .env.example"
    warn "→ Edit $ENV_FILE with your credentials."
    cp "$ROOT/.env.example" "$ENV_FILE"
  fi

  # Kill both child process groups cleanly on Ctrl-C
  trap 'echo ""; log "Stopping…"; kill 0 2>/dev/null; wait 2>/dev/null' INT TERM

  echo ""
  echo -e "  ${CYAN}${BOLD}Backend${RESET}   → ${BOLD}http://localhost:8000/api/docs${RESET}  ${DIM}(uvicorn --reload)${RESET}"
  echo -e "  ${GREEN}${BOLD}Frontend${RESET}  → ${BOLD}http://localhost:5173${RESET}           ${DIM}(vite --host)${RESET}"
  echo ""

  # ── Backend subprocess ────────────────────────────────────────────────────
  (
    cd "$BACKEND"
    # shellcheck disable=SC1091
    source "$VENV/bin/activate"
    # PYTHONUNBUFFERED=1  → flush every log line immediately, no block-buffering
    PYTHONUNBUFFERED=1 uvicorn app.main:app \
      --reload \
      --host 0.0.0.0 \
      --port 8000 \
      --log-level info \
      --access-log 2>&1 \
    | prefix_be
  ) &
  BE_PID=$!

  # ── Frontend subprocess ───────────────────────────────────────────────────
  (
    cd "$FRONTEND"
    npm run dev -- --host 2>&1 \
    | prefix_fe
  ) &
  FE_PID=$!

  # Wait for both; if either exits unexpectedly, kill the other
  wait "$BE_PID" || { err "Backend exited unexpectedly (exit $?)"; kill "$FE_PID" 2>/dev/null; }
  wait "$FE_PID" || { err "Frontend exited unexpectedly (exit $?)"; kill "$BE_PID" 2>/dev/null; }
}

# ── Run tests ─────────────────────────────────────────────────────────────────
run_tests() {
  require python3.14
  if [[ ! -d "$VENV" ]]; then
    warn "Venv not found. Running setup first…"
    setup
  fi
  log "Running backend tests…"
  cd "$BACKEND"
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  PYTHONUNBUFFERED=1 python -m pytest tests/ -v --tb=short "$@"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
MODE="${1:-both}"

case "$MODE" in
  setup)    setup ;;
  backend)  start_backend ;;
  frontend) start_frontend ;;
  both)     start_both ;;
  test)     shift; run_tests "$@" ;;
  *)
    echo -e "Usage: ${BOLD}./dev.sh${RESET} [setup|backend|frontend|both|test]"
    exit 1
    ;;
esac
