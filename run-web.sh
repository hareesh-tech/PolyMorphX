#!/usr/bin/env bash
#
# Start the PolyMorph web console — Linux / macOS
# Launches the FastAPI backend (:8123) and the Vite frontend (:5173).
# Ctrl+C stops both.
#
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

# sanity: setup must have run
[ -x "./.venv/bin/python" ] || { echo "ERROR: engine venv missing. Run ./setup.sh first."; exit 1; }
[ -x "./web/backend/.venv/bin/python" ] || { echo "ERROR: backend venv missing. Run ./setup.sh first."; exit 1; }
[ -d "./web/frontend/node_modules" ] || { echo "ERROR: frontend deps missing. Run ./setup.sh first."; exit 1; }

# point the backend at the engine venv (has pefile/capstone/keystone/lief)
export POLYMORPH_PYTHON="$ROOT/.venv/bin/python"

echo "Starting backend  -> http://127.0.0.1:8123"
( cd web/backend && ./.venv/bin/python -m uvicorn app.main:app --port 8123 ) &
BACK=$!

echo "Starting frontend -> http://localhost:5173"
( cd web/frontend && npm run dev ) &
FRONT=$!

trap 'echo; echo "Stopping..."; kill "$BACK" "$FRONT" 2>/dev/null || true' EXIT INT TERM
wait
