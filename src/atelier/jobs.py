"""In-process async generation job queue."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from atelier.backends.pipeline import run_generate
from atelier.backends.registry import BackendRegistry
from atelier.backends.types import AtelierError, GenerateRequest
from atelier.graph.models import MediaNode
from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.pending
    request: dict[str, Any] = Field(default_factory=dict)
    nodes: list[MediaNode] = Field(default_factory=list)
    error: dict[str, str] | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobQueue:
    """Background asyncio tasks for long-running generation (e.g. video)."""

    def __init__(
        self,
        *,
        registry: BackendRegistry,
        graph: GraphStore,
        media: MediaStore,
        max_finished: int = 100,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._registry = registry
        self._graph = graph
        self._media = media
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._max_finished = max_finished
        self._tasks: set[asyncio.Task[None]] = set()
        self._on_complete = on_complete

    def bind_stores(self, graph: GraphStore, media: MediaStore) -> None:
        """Point at the active lineage stores after a switch."""
        self._graph = graph
        self._media = media

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self, *, limit: int = 50) -> list[Job]:
        items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        return items[:limit]

    async def submit(self, request: GenerateRequest) -> Job:
        job = Job(request=request.model_dump(mode="json"))
        async with self._lock:
            self._jobs[job.id] = job
            self._prune_finished_locked()
        task = asyncio.create_task(self._run(job.id, request), name=f"job-{job.id[:8]}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def _prune_finished_locked(self) -> None:
        finished = [j for j in self._jobs.values() if j.status in (JobStatus.done, JobStatus.failed)]
        finished.sort(key=lambda j: j.finished_at or j.updated_at)
        while len(finished) > self._max_finished:
            old = finished.pop(0)
            self._jobs.pop(old.id, None)

    async def _run(self, job_id: str, request: GenerateRequest) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = JobStatus.running
        job.started_at = _utc_now()
        job.updated_at = job.started_at
        try:
            nodes = await run_generate(
                request,
                registry=self._registry,
                graph=self._graph,
                media=self._media,
            )
            job.nodes = nodes
            job.status = JobStatus.done
            job.error = None
        except AtelierError as e:
            log.warning("job %s failed: %s", job_id, e.message)
            job.status = JobStatus.failed
            job.error = e.to_dict()
        except Exception as e:
            log.exception("job %s crashed", job_id)
            job.status = JobStatus.failed
            job.error = {"error": "generation_failed", "detail": str(e)}
        finally:
            job.finished_at = _utc_now()
            job.updated_at = job.finished_at
            if self._on_complete is not None:
                try:
                    self._on_complete()
                except Exception:
                    log.exception("job on_complete failed")
