"""HTTP API routes."""

from fastapi import APIRouter

from atelier.api.generate import router as generate_router
from atelier.api.lineages import router as lineages_router
from atelier.api.media import router as media_router


def build_api_router() -> APIRouter:
    root = APIRouter()
    root.include_router(media_router)
    root.include_router(generate_router)
    root.include_router(lineages_router)
    return root
