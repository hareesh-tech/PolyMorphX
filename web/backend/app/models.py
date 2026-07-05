from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StageInfo(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class JobSummary(BaseModel):
    id: str
    status: JobStatus
    input_name: str
    created_at: datetime


class JobDetail(JobSummary):
    stages: list[StageInfo]
    error: Optional[str] = None


class LogEvent(BaseModel):
    """One line of output plus whatever structured meaning we could infer from it."""

    type: str  # "log" | "stage_started" | "stage_completed" | "stage_failed" | "job_completed" | "job_failed"
    message: str
    stage: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArtifactInfo(BaseModel):
    name: str
    size_bytes: int
