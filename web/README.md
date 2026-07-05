# PolyMorph Web Console

A web frontend for the PolyMorph binary transformation pipeline. This does not
replace `gui.py` (the PyQt desktop app) or the `modules/orchestrator.py` CLI —
it's a third way to drive the same engine, over HTTP instead of Qt or argv.

```
web/
├── backend/     FastAPI service that runs modules/orchestrator.py as a subprocess
│                and streams its log output over a WebSocket
└── frontend/    React + Vite + Tailwind + Framer Motion UI
```

## How it fits together

The backend never reimplements the engine — it shells out to
`modules/orchestrator.py` exactly like `gui.py` does, then classifies each log
line into structured events (`stage_started`, `job_completed`, `job_failed`)
so the frontend can animate a pipeline tracker instead of just dumping text.

Because the engine's dependencies (`pefile`, `capstone`, `keystone`) live in
the top-level `PolyMorphic/.venv`, not in `web/backend`'s own venv, the
backend resolves which Python to use for the orchestrator subprocess via
`app/config.py::ENGINE_PYTHON`:

1. `POLYMORPH_PYTHON` env var, if set
2. `PolyMorphic/.venv` (Windows: `Scripts/python.exe`, POSIX: `bin/python`)
3. `PolyMorphX/.venv`
4. falls back to whatever interpreter runs the backend itself

If your engine venv lives somewhere non-standard, set `POLYMORPH_PYTHON`
before starting the backend.

## Running locally

**Backend** (from `web/backend`):

```bash
python -m venv .venv
.venv/Scripts/activate          # or source .venv/bin/activate on POSIX
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8123
```

**Frontend** (from `web/frontend`):

```bash
npm install
npm run dev
```

Open the Vite dev server URL (default `http://localhost:5173`). It proxies
`/api/*` (HTTP and WebSocket) to `http://127.0.0.1:8123`, so no CORS/env
juggling is needed in dev — see `vite.config.ts`.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/jobs` | Upload a binary (+ optional config.json override + orchestrator options), starts a job |
| GET | `/api/jobs` | List jobs |
| GET | `/api/jobs/{id}` | Job status + per-stage progress |
| GET | `/api/jobs/{id}/logs` | Full log backlog (non-streaming) |
| WS | `/api/jobs/{id}/stream` | Live log/event stream |
| GET | `/api/jobs/{id}/artifacts` | List output files |
| GET | `/api/jobs/{id}/artifacts/{name}` | Download an output file |

Job state and uploaded files are kept in `web/backend/jobs_storage/<job_id>/`
(gitignored) — nothing is persisted beyond disk, there's no database yet.

## Known limitations (MVP)

- Single-process job store: restarting the backend loses job history.
- Stage progress is inferred by regex-matching the orchestrator's existing
  log lines (`==== Executing X ===`, `Orchestration completed successfully.`)
  rather than the engine emitting structured events natively. Good enough
  for a progress tracker; not a substitute for real telemetry.
- No auth — do not expose this beyond localhost/a trusted network as-is,
  since it accepts arbitrary file uploads and runs a subprocess per job.
- The CFG graph / instruction-diff visualizations described in the original
  plan aren't built yet; this pass covers upload → animated stage tracker →
  live console → artifact download.
