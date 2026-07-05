import asyncio
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from ..config import DEFAULT_CONFIG_PATH
from ..models import ArtifactInfo, JobDetail, JobSummary
from ..services.analytics import build_analytics
from ..services.job_manager import job_manager
from ..services.orchestrator_runner import run_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobDetail)
async def create_job(
    file: UploadFile = File(...),
    config: Optional[UploadFile] = File(None),
    count: Optional[int] = Form(None),
    cfg_count: Optional[int] = Form(None),
    cfg_enable_subset: bool = Form(True),
    cfg_subset_pct: Optional[float] = Form(None),
    cfg_seed: Optional[int] = Form(None),
    divide_transform: bool = Form(False),
    verbose: bool = Form(False),
    quiet: bool = Form(False),
):
    if not file.filename:
        raise HTTPException(400, "Missing input file")

    job = job_manager.create_job(input_name=file.filename, config_path=DEFAULT_CONFIG_PATH)

    input_path = job.input_dir / Path(file.filename).name
    with input_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    job.input_path = input_path

    if config is not None and config.filename:
        custom_config_path = job.job_dir / "config.json"
        with custom_config_path.open("wb") as out:
            shutil.copyfileobj(config.file, out)
        job.config_path = custom_config_path
        job.reload_stages()

    params = dict(
        count=count,
        cfg_count=cfg_count,
        cfg_enable_subset=cfg_enable_subset,
        cfg_subset_pct=cfg_subset_pct,
        cfg_seed=cfg_seed,
        divide_transform=divide_transform,
        verbose=verbose,
        quiet=quiet,
    )

    job.task = asyncio.create_task(run_job(job, params))
    return job.detail()


@router.get("", response_model=list[JobSummary])
async def list_jobs():
    return [j.summary() for j in job_manager.list()]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.detail()


@router.get("/{job_id}/logs")
async def get_logs(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return [e.model_dump(mode="json") for e in job.log_buffer]


@router.websocket("/{job_id}/stream")
async def stream_logs(websocket: WebSocket, job_id: str):
    job = job_manager.get(job_id)
    if not job:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    for event in job.log_buffer:
        await websocket.send_json(event.model_dump(mode="json"))

    if job.status in ("completed", "failed"):
        await websocket.close()
        return

    queue = job.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event.model_dump(mode="json"))
            if event.type in ("job_completed", "job_failed"):
                break
    except WebSocketDisconnect:
        pass
    finally:
        job.unsubscribe(queue)


@router.get("/{job_id}/analytics")
async def get_analytics(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return build_analytics(job)


@router.get("/{job_id}/artifacts", response_model=list[ArtifactInfo])
async def list_artifacts(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.output_dir.exists():
        return []
    return [
        ArtifactInfo(name=p.name, size_bytes=p.stat().st_size)
        for p in sorted(job.output_dir.iterdir())
        if p.is_file()
    ]


@router.get("/{job_id}/artifacts/{filename}")
async def download_artifact(job_id: str, filename: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    safe_name = Path(filename).name
    resolved_dir = job.output_dir.resolve()
    path = (resolved_dir / safe_name).resolve()

    if path.parent != resolved_dir or not path.is_file():
        raise HTTPException(404, "Artifact not found")

    return FileResponse(path, filename=safe_name)
