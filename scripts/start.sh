#!/usr/bin/env bash
# One-command dev launcher for MIDI Remaster Lab (macOS / Linux).
# Proposal citation: Deliverable 4 (demo app); ONBOARDING_REPORT §D item #7.
#
# Usage (from repo root):
#   bash scripts/start.sh
#   # or:
#   chmod +x scripts/start.sh && ./scripts/start.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"
BACKEND_PORT="${BACKEND_PORT:-8001}"
INSTALL_ML="${INSTALL_ML:-0}"

# ── Color helpers ──────────────────────────────────────────────────────────
cyan() { printf '\033[0;36m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
red() { printf '\033[0;31m%s\033[0m\n' "$*"; }

# ── Preflight ──────────────────────────────────────────────────────────────
check_cmd() { command -v "$1" &>/dev/null || { yellow "  [WARN] '$1' not on PATH — $2"; }; }

echo ""
cyan "[start.sh] MIDI Remaster Lab — dev launcher"
echo ""

check_cmd python3 "Install Python 3.11+"
check_cmd node    "Install Node.js 18+"
check_cmd fluidsynth "Audio rendering will be unavailable"
check_cmd lame    "MP3 conversion will be unavailable"

if [[ ! -f "$BACKEND/venv/bin/activate" ]]; then
    cyan "[start.sh] Creating backend virtual environment..."
    python3 -m venv "$BACKEND/venv"
fi
if [[ ! -d "$FRONTEND/node_modules" ]]; then
    cyan "[start.sh] Installing frontend dependencies..."
    (cd "$FRONTEND" && npm install)
fi

# ── Install baseline dependencies by default ──────────────────────────────
mkdir -p "$REPO_ROOT/MLtraining"
VENV_PIP="$BACKEND/venv/bin/pip"
VENV_PY="$BACKEND/venv/bin/python"
"$VENV_PIP" install -q -r "$BACKEND/requirements.txt"

# ── Optional ML dependencies ─────────────────────────────────────────────
if [[ "$INSTALL_ML" == "1" ]]; then
    cyan "[start.sh] Installing optional ML dependencies..."
    "$VENV_PIP" install -q -r "$BACKEND/requirements-ml.txt"
    "$VENV_PIP" install -q "git+https://github.com/facebookresearch/audiocraft.git"
    green "[start.sh] ML dependencies ready."
else
    yellow "[start.sh] ML dependencies skipped (set INSTALL_ML=1 to install)."
fi

# ── Start backend ──────────────────────────────────────────────────────────
cyan "[start.sh] Starting backend on http://localhost:$BACKEND_PORT ..."
(
    cd "$BACKEND"
    if [[ -f venv/bin/activate ]]; then source venv/bin/activate; fi
    python -m uvicorn src.api:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload
) &
BACKEND_PID=$!

sleep 2  # let backend initialize before frontend hits /health

# ── Start frontend ─────────────────────────────────────────────────────────
cyan "[start.sh] Starting frontend on http://localhost:3000 ..."
(
    cd "$FRONTEND"
    npm run dev
) &
FRONTEND_PID=$!

echo ""
green "  Backend : http://localhost:$BACKEND_PORT/health  (PID $BACKEND_PID)"
green "  Frontend: http://localhost:3000                  (PID $FRONTEND_PID)"
yellow "  Press Ctrl+C to stop both servers."
echo ""

# Wait and trap Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; yellow '[start.sh] Servers stopped.'; exit 0" INT TERM
wait
