#!/usr/bin/env bash
#
# PolyMorph one-shot setup — Linux / macOS
# Creates all virtualenvs, installs every dependency, and leaves the
# project ready to run (CLI + web console).
#
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

echo "=================================================="
echo " PolyMorph setup (Linux / macOS)"
echo "=================================================="

# ---- prerequisite checks ----
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found. Install Python 3.8+ and re-run."; exit 1; }
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PYOK=$(python3 -c 'import sys; print(1 if sys.version_info[:2] >= (3,8) else 0)')
[ "$PYOK" = "1" ] || { echo "ERROR: Python 3.8+ required (found $PYV)."; exit 1; }
echo " Python $PYV  OK"

command -v node >/dev/null 2>&1 || { echo "ERROR: Node.js not found. Install Node 18+ and re-run."; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "ERROR: npm not found. Install Node.js (includes npm) and re-run."; exit 1; }
echo " Node $(node -v)  OK"
echo

# ---- 1. engine venv (also used by the web backend as the orchestrator interpreter) ----
echo "==> [1/3] Engine virtualenv (.venv) + dependencies"
python3 -m venv .venv
"./.venv/bin/python" -m pip install --upgrade pip >/dev/null
"./.venv/bin/pip" install -r requirements.txt
echo

# ---- 2. web backend venv ----
echo "==> [2/3] Web backend virtualenv (web/backend/.venv) + dependencies"
python3 -m venv web/backend/.venv
"./web/backend/.venv/bin/python" -m pip install --upgrade pip >/dev/null
"./web/backend/.venv/bin/pip" install -r web/backend/requirements.txt
echo

# ---- 3. web frontend deps ----
echo "==> [3/3] Web frontend dependencies (npm install)"
( cd web/frontend && npm install )
echo

echo "=================================================="
echo " Setup complete."
echo
echo " Start the web console:"
echo "     ./run-web.sh          (then open http://localhost:5173)"
echo
echo " Or run the CLI directly:"
echo "     ./.venv/bin/python modules/orchestrator.py \\"
echo "         --input <your_binary.exe> --config modules/config.json \\"
echo "         --output ./Output --cfg-seed 1234 -v"
echo "=================================================="
