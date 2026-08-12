"""HTTP API routes."""

from fastapi import APIRouter

from atelier.api.media import router as media_router


def build_api_router() -> APIRouter:
    root = APIRouter()
    root.include_router(media_router)
    return root
