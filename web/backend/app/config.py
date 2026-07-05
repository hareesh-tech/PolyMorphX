"""Paths shared across the backend.

Layout assumption: this file lives at <PolyMorphX>/web/backend/app/config.py,
so the PolyMorph engine (the `modules/` package + orchestrator.py) is three
levels up.
"""

import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
WEB_DIR = BACKEND_DIR.parent
POLYMORPH_ROOT = WEB_DIR.parent

MODULES_DIR = POLYMORPH_ROOT / "modules"
ORCHESTRATOR_SCRIPT = MODULES_DIR / "orchestrator.py"
DEFAULT_CONFIG_PATH = MODULES_DIR / "config.json"

JOBS_DIR = BACKEND_DIR / "jobs_storage"
JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_engine_python() -> str:
    """The orchestrator subprocess needs pefile/capstone/keystone, which live in
    the PolyMorph engine's own virtualenv (POLYMORPH_ROOT/../.venv) -- NOT this
    backend's venv. Override with the POLYMORPH_PYTHON env var if that venv
    lives somewhere else.
    """
    override = os.environ.get("POLYMORPH_PYTHON")
    if override:
        return override

    candidates = [
        POLYMORPH_ROOT.parent / ".venv" / "Scripts" / "python.exe",  # Windows, PolyMorphic/.venv
        POLYMORPH_ROOT.parent / ".venv" / "bin" / "python",  # POSIX
        POLYMORPH_ROOT / ".venv" / "Scripts" / "python.exe",
        POLYMORPH_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return sys.executable


ENGINE_PYTHON = _resolve_engine_python()
