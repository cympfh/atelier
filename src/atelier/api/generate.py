"""Generate + backends + jobs HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from atelier.backends.pipeline import run_generate
from atelier.backends.types import (
    AtelierError,
    GenerateMode,
    GenerateRequest,
)
from atelier.graph.models import MediaNode
from atelier.jobs import Job, JobStatus
from atelier.refs import resolve_media_ids

router = APIRouter(tags=["generate"])


class GenerateBody(BaseModel):
    mode: GenerateMode
    backend: str
    prompt: str = ""
    media_ids: list[str] = Field(default_factory=list)
    # Ordered input slots for @ImageN resolution (optional; defaults to media_ids)
    input_slots: list[str] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # If true, parse @ImageN/@VideoN in prompt
    resolve_at_refs: bool = True
    # Async job queue (recommended for video)
    async_job: bool = False


class GenerateResponse(BaseModel):
    nodes: list[MediaNode]
    job_id: str | None = None
    status: str | None = None


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    request: dict[str, Any]
    nodes: list[MediaNode]
    error: dict[str, str] | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


def _http_error(exc: AtelierError) -> HTTPException:
    status = {
        "backend_not_found": 404,
        "backend_unavailable": 503,
        "mode_not_supported": 400,
        "media_not_found": 404,
        "invalid_request": 400,
        "generation_failed": 502,
    }.get(exc.code, 400)
    return HTTPException(status_code=status, detail=exc.to_dict())


def _job_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        status=job.status,
        request=job.request,
        nodes=job.nodes,
        error=job.error,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


def _build_request(body: GenerateBody, request: Request) -> GenerateRequest:
    graph = request.app.state.graph_store
    prompt = body.prompt
    media_ids = list(body.media_ids)

    if body.resolve_at_refs and "@" in prompt:
        slots = body.input_slots if body.input_slots is not None else body.media_ids
        if slots:
            prompt, ref_ids = resolve_media_ids(prompt, slot_ids=slots)
        else:
            prompt, ref_ids = resolve_media_ids(prompt, candidates=graph.list_nodes())
        for mid in ref_ids:
            if mid not in media_ids:
                media_ids.append(mid)

    return GenerateRequest(
        mode=body.mode,
        backend=body.backend,
        prompt=prompt,
        media_ids=media_ids,
        params=body.params,
    )


@router.get("/api/backends")
def list_backends(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.backend_registry
    return registry.list_detail()


@router.get("/api/graph")
def get_graph(request: Request) -> dict[str, Any]:
    snap = request.app.state.graph_store.snapshot()
    return snap.model_dump(mode="json")


@router.get("/api/jobs", response_model=list[JobResponse])
def list_jobs(request: Request, limit: int = 50) -> list[JobResponse]:
    queue = request.app.state.job_queue
    return [_job_response(j) for j in queue.list_jobs(limit=limit)]


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, request: Request) -> JobResponse:
    job = request.app.state.job_queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "detail": job_id})
    return _job_response(job)


@router.get("/api/sd/models")
async def sd_models(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.backend_registry
    try:
        backend = registry.get("sd_webui")
    except AtelierError as e:
        raise _http_error(e) from e
    list_models = getattr(backend, "list_models", None)
    if not callable(list_models):
        raise HTTPException(status_code=501, detail={"error": "not_supported", "detail": "no sd backend"})
    available, reason = backend.availability()
    if not available:
        raise HTTPException(
            status_code=503,
            detail={"error": "backend_unavailable", "detail": reason or "sd unavailable"},
        )
    try:
        return await list_models()
    except AtelierError as e:
        raise _http_error(e) from e


@router.post("/api/generate", response_model=GenerateResponse)
async def generate(body: GenerateBody, request: Request) -> GenerateResponse:
    registry = request.app.state.backend_registry
    graph = request.app.state.graph_store
    media = request.app.state.media_store
    queue = request.app.state.job_queue

    try:
        req = _build_request(body, request)
    except AtelierError as e:
        raise _http_error(e) from e

    # Fail fast before enqueueing (same checks as pipeline)
    try:
        backend = registry.get(req.backend)
        available, reason = backend.availability()
        if not available:
            from atelier.backends.types import BackendUnavailableError

            raise BackendUnavailableError(req.backend, reason)
        if not backend.capabilities().supports(req.mode):
            from atelier.backends.types import ModeNotSupportedError

            raise ModeNotSupportedError(req.backend, req.mode)
    except AtelierError as e:
        raise _http_error(e) from e

    # Auto-async for video modes; body.async_job forces async for any mode.
    use_async = body.async_job or body.mode in (GenerateMode.t2v, GenerateMode.i2v)

    if use_async:
        job = await queue.submit(req)
        return GenerateResponse(nodes=[], job_id=job.id, status=job.status.value)

    try:
        nodes = await run_generate(req, registry=registry, graph=graph, media=media)
    except AtelierError as e:
        raise _http_error(e) from e

    return GenerateResponse(nodes=nodes, job_id=None, status="done")
