"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from atelier import __version__
from atelier.config import Settings, get_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.ensure_data_dir()

    app = FastAPI(title="atelier", version=__version__)
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return index_path.read_text(encoding="utf-8")
        return (
            "<!DOCTYPE html><html><head><title>atelier</title></head>" "<body><h1>atelier</h1><p>ok</p></body></html>"
        )

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
