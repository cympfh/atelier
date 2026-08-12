"""Generate + backends HTTP API."""

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


class GenerateResponse(BaseModel):
    nodes: list[MediaNode]


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


@router.get("/api/backends")
def list_backends(request: Request) -> list[dict[str, Any]]:
    registry = request.app.state.backend_registry
    return registry.list_detail()


@router.get("/api/graph")
def get_graph(request: Request) -> dict[str, Any]:
    snap = request.app.state.graph_store.snapshot()
    return snap.model_dump(mode="json")


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

    prompt = body.prompt
    media_ids = list(body.media_ids)

    if body.resolve_at_refs and "@" in prompt:
        slots = body.input_slots if body.input_slots is not None else body.media_ids
        try:
            if slots:
                prompt, ref_ids = resolve_media_ids(prompt, slot_ids=slots)
            else:
                prompt, ref_ids = resolve_media_ids(prompt, candidates=graph.list_nodes())
        except AtelierError as e:
            raise _http_error(e) from e
        # refs first, then explicit ids
        for mid in ref_ids:
            if mid not in media_ids:
                media_ids.append(mid)

    req = GenerateRequest(
        mode=body.mode,
        backend=body.backend,
        prompt=prompt,
        media_ids=media_ids,
        params=body.params,
    )

    try:
        nodes = await run_generate(req, registry=registry, graph=graph, media=media)
    except AtelierError as e:
        raise _http_error(e) from e

    return GenerateResponse(nodes=nodes)
