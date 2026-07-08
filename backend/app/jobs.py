"""
In-memory job tracking.

This is intentionally simple for an MVP: a dict guarded by a lock, with a
thread pool running the pipeline. It works fine for a single-process
deployment. If you need to scale beyond one server process, swap this for
Celery + Redis (or RQ) — the JobStore interface below is the seam to do that;
`pipeline.run_pipeline` doesn't know or care how it's invoked.
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    SEPARATING = "separating"
    TRANSCRIBING = "transcribing"
    RENDERING = "rendering"
    ENGRAVING = "engraving"
    DONE = "done"
    ERROR = "error"


@dataclass
class Job:
    id: str
    youtube_url: str
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0  # 0-100
    message: str = ""
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    # Output file paths, populated as the pipeline completes each stage.
    midi_path: Optional[str] = None
    piano_audio_path: Optional[str] = None
    musicxml_path: Optional[str] = None


class JobStore:
    def __init__(self, max_workers: int = 2):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def create(self, youtube_url: str) -> Job:
        job = Job(id=str(uuid.uuid4()), youtube_url=youtube_url)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for k, v in kwargs.items():
                setattr(job, k, v)

    def submit(self, job_id: str, fn, *args, **kwargs):
        """Run fn(job_id, *args, **kwargs) in the background thread pool."""
        self._executor.submit(fn, job_id, *args, **kwargs)


# Single shared instance used by the FastAPI app.
job_store = JobStore(max_workers=2)
