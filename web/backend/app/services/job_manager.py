import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import JOBS_DIR
from ..models import JobDetail, JobStatus, JobSummary, LogEvent, StageInfo, StageStatus


def _stage_names_from_config(config_path: Path) -> list[str]:
    """Derive the pipeline stage list from a PolyMorph config.json's technique paths."""
    try:
        data = json.loads(config_path.read_text())
        techniques = data.get("modules", {}).get("start", {}).get("techniques", [])
        return [Path(t["path"]).stem for t in techniques]
    except Exception:
        return []


class Job:
    def __init__(self, job_id: str, input_name: str, job_dir: Path, config_path: Path):
        self.id = job_id
        self.input_name = input_name
        self.status = JobStatus.PENDING
        self.created_at = datetime.now(timezone.utc)
        self.job_dir = job_dir
        self.input_dir = job_dir / "input"
        self.output_dir = job_dir / "output"
        self.config_path = config_path
        self.input_path: Optional[Path] = None
        self.error: Optional[str] = None

        self.stages: list[StageInfo] = [StageInfo(name=n) for n in (_stage_names_from_config(config_path) or ["pipeline"])]
        self.log_buffer: list[LogEvent] = []
        self.subscribers: list[asyncio.Queue] = []
        self.process: Optional[asyncio.subprocess.Process] = None
        self.task: Optional[asyncio.Task] = None

    def reload_stages(self):
        self.stages = [StageInfo(name=n) for n in (_stage_names_from_config(self.config_path) or ["pipeline"])]

    def summary(self) -> JobSummary:
        return JobSummary(id=self.id, status=self.status, input_name=self.input_name, created_at=self.created_at)

    def detail(self) -> JobDetail:
        return JobDetail(**self.summary().model_dump(), stages=self.stages, error=self.error)

    def _find_stage(self, name: str) -> Optional[StageInfo]:
        return next((s for s in self.stages if s.name == name), None)

    async def emit(self, event: LogEvent):
        self.log_buffer.append(event)

        if event.type == "stage_started" and event.stage:
            for s in self.stages:
                if s.status == StageStatus.RUNNING:
                    s.status = StageStatus.COMPLETED
                    s.completed_at = event.timestamp
            stage = self._find_stage(event.stage)
            if stage:
                stage.status = StageStatus.RUNNING
                stage.started_at = event.timestamp
        elif event.type == "job_completed":
            for s in self.stages:
                if s.status != StageStatus.FAILED:
                    if s.status == StageStatus.RUNNING:
                        s.completed_at = event.timestamp
                    s.status = StageStatus.COMPLETED
        elif event.type == "job_failed":
            for s in self.stages:
                if s.status == StageStatus.RUNNING:
                    s.status = StageStatus.FAILED
                    s.completed_at = event.timestamp

        dead = []
        for q in self.subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.subscribers.remove(q)

    def subscribe(self) -> "asyncio.Queue[LogEvent]":
        q: "asyncio.Queue[LogEvent]" = asyncio.Queue(maxsize=1000)
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: "asyncio.Queue[LogEvent]"):
        if q in self.subscribers:
            self.subscribers.remove(q)


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create_job(self, input_name: str, config_path: Path) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job_dir = JOBS_DIR / job_id
        job = Job(job_id, input_name, job_dir, config_path)
        job.input_dir.mkdir(parents=True, exist_ok=True)
        job.output_dir.mkdir(parents=True, exist_ok=True)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)


job_manager = JobManager()
