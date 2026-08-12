"""Lineage list / switch / rename / save API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from atelier.lineage import LineageMeta

router = APIRouter(prefix="/api/lineages", tags=["lineages"])


class CreateLineageBody(BaseModel):
    name: str | None = None


class RenameBody(BaseModel):
    name: str = Field(min_length=1)


class SwitchBody(BaseModel):
    id: str


def _lm(request: Request):
    return request.app.state.lineage_manager


@router.get("", response_model=list[LineageMeta])
def list_lineages(request: Request) -> list[LineageMeta]:
    return _lm(request).list_all()


@router.get("/current", response_model=LineageMeta)
def current_lineage(request: Request) -> LineageMeta:
    return _lm(request).current()


def _sync(request: Request) -> None:
    sync = getattr(request.app.state, "sync_active_stores", None)
    if callable(sync):
        sync()


@router.post("", response_model=LineageMeta, status_code=201)
def create_lineage(body: CreateLineageBody, request: Request) -> LineageMeta:
    lm = _lm(request)
    meta = lm.create(body.name)
    lm.switch(meta.id)
    _sync(request)
    return meta


@router.post("/current", response_model=LineageMeta)
def switch_lineage(body: SwitchBody, request: Request) -> LineageMeta:
    lm = _lm(request)
    try:
        lm.switch(body.id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"error": "lineage_not_found", "detail": body.id}) from e
    _sync(request)
    return lm.current()


@router.patch("/{lineage_id}", response_model=LineageMeta)
def rename_lineage(lineage_id: str, body: RenameBody, request: Request) -> LineageMeta:
    try:
        return _lm(request).rename(lineage_id, body.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail={"error": "lineage_not_found", "detail": lineage_id}) from e


@router.post("/current/save", response_model=LineageMeta)
def save_current(request: Request) -> LineageMeta:
    """Explicit / autosave flush of graph + meta.updated_at."""
    return _lm(request).save_now()
