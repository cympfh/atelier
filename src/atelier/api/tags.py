"""Tag catalog API (prompt suggest for SD / danbooru-style prompts)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from atelier.tags import load_tags_catalog

router = APIRouter()


@router.get("/api/tags")
def get_tags(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    path = settings.resolve_tags_toml()
    if path is None:
        return {
            "path": None,
            "groups": [],
            "tags": [],
            "negative_tags": [],
            "available": False,
        }
    try:
        catalog = load_tags_catalog(path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "tags_load_failed", "detail": str(e)},
        ) from e
    catalog["available"] = True
    return catalog
