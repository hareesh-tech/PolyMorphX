"""Runs modules/orchestrator.py as a subprocess and turns its log lines into
structured events the frontend's pipeline tracker can animate against.
"""

import asyncio
import re

from ..config import ENGINE_PYTHON, ORCHESTRATOR_SCRIPT, POLYMORPH_ROOT
from ..models import JobStatus, LogEvent
from .job_manager import Job

_LEVEL_RE = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL): (.*)$")
_STAGE_RE = re.compile(r"^==== Executing (\S+) ===$")
_FAIL_RE = re.compile(r"^Pipeline failed at step \d+: (.*)$")
_DONE_RE = re.compile(r"^Orchestration completed successfully\.$")


def classify_line(raw_line: str) -> LogEvent:
    stripped = raw_line.rstrip("\n").rstrip("\r")
    content_match = _LEVEL_RE.match(stripped)
    content = content_match.group(2) if content_match else stripped

    stage_match = _STAGE_RE.match(content)
    if stage_match:
        return LogEvent(type="stage_started", message=stripped, stage=stage_match.group(1))

    fail_match = _FAIL_RE.match(content)
    if fail_match:
        return LogEvent(type="job_failed", message=stripped)

    if _DONE_RE.match(content):
        return LogEvent(type="job_completed", message=stripped)

    return LogEvent(type="log", message=stripped)


def build_command(job: Job, params: dict) -> list[str]:
    assert job.input_path is not None, "input file must be saved before starting the job"

    cmd = [
        ENGINE_PYTHON,
        str(ORCHESTRATOR_SCRIPT),
        "--input", str(job.input_path),
        "--config", str(job.config_path),
        "--output", str(job.output_dir),
    ]

    if params.get("count") is not None:
        cmd += ["--count", str(params["count"])]
    if params.get("cfg_count") is not None:
        cmd += ["--cfg-count", str(params["cfg_count"])]

    cmd.append("--cfg-enable-subset" if params.get("cfg_enable_subset", True) else "--cfg-no-subset")

    if params.get("cfg_subset_pct") is not None:
        cmd += ["--cfg-subset-pct", str(params["cfg_subset_pct"])]
    if params.get("cfg_seed") is not None:
        cmd += ["--cfg-seed", str(params["cfg_seed"])]
    if params.get("divide_transform"):
        cmd.append("--divide-transform")
    if params.get("verbose"):
        cmd.append("-v")
    if params.get("quiet"):
        cmd.append("-q")

    return cmd


async def run_job(job: Job, params: dict):
    job.status = JobStatus.RUNNING
    cmd = build_command(job, params)
    await job.emit(LogEvent(type="log", message=f"$ {' '.join(cmd)}"))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(POLYMORPH_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        await job.emit(LogEvent(type="job_failed", message=f"Failed to launch orchestrator: {e}"))
        return

    job.process = proc
    assert proc.stdout is not None

    async for raw_line in proc.stdout:
        event = classify_line(raw_line.decode(errors="replace"))
        if event.type == "job_failed" and not job.error:
            job.error = event.message
        await job.emit(event)

    returncode = await proc.wait()

    if returncode == 0 and job.status != JobStatus.FAILED:
        job.status = JobStatus.COMPLETED
        if not any(e.type == "job_completed" for e in job.log_buffer):
            await job.emit(LogEvent(type="job_completed", message="Orchestration completed successfully."))
    else:
        job.status = JobStatus.FAILED
        if not job.error:
            job.error = f"Process exited with code {returncode}"
        await job.emit(LogEvent(type="job_failed", message=job.error))
