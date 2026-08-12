"""Media list / get / upload HTTP API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from atelier.graph.models import MediaNode
from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore, kind_from_mime, mime_from_filename

router = APIRouter(prefix="/api/media", tags=["media"])


def _graph(request: Request) -> GraphStore:
    return request.app.state.graph_store


def _media(request: Request) -> MediaStore:
    return request.app.state.media_store


@router.get("", response_model=list[MediaNode])
def list_media(request: Request) -> list[MediaNode]:
    return _graph(request).list_nodes()


@router.get("/{node_id}", response_model=MediaNode)
def get_media(node_id: str, request: Request) -> MediaNode:
    node = _graph(request).get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"media not found: {node_id}")
    return node


@router.get("/{node_id}/file")
def get_media_file(node_id: str, request: Request) -> FileResponse:
    graph = _graph(request)
    store = _media(request)
    node = graph.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"media not found: {node_id}")
    path = store.path_for_node(node)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"file missing: {node_id}")
    download_name = node.original_name or node.filename
    return FileResponse(
        path,
        media_type=node.mime,
        filename=download_name,
    )


@router.post("/upload", response_model=MediaNode, status_code=201)
async def upload_media(
    request: Request,
    file: Annotated[UploadFile, File(...)],
) -> MediaNode:
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    original = file.filename or "upload.bin"
    content_type = (file.content_type or "").split(";")[0].strip()
    if not content_type or content_type == "application/octet-stream":
        content_type = mime_from_filename(original)

    try:
        kind_from_mime(content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    store = _media(request)
    graph = _graph(request)
    node = store.save_bytes(
        raw,
        mime=content_type,
        backend="upload",
        original_name=original,
    )
    graph.add_node(node)
    lm = getattr(request.app.state, "lineage_manager", None)
    if lm is not None:
        try:
            lm.touch()
        except Exception:
            pass
    return node
