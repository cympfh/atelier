"""FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from atelier import __version__
from atelier.api import build_api_router
from atelier.backends import build_default_registry
from atelier.config import Settings, get_settings
from atelier.jobs import JobQueue
from atelier.lineage import LineageManager

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, *, include_echo: bool = False) -> FastAPI:
    settings = settings or get_settings()
    data_dir = settings.ensure_data_dir()

    lineages = LineageManager(data_dir)
    registry = build_default_registry(settings, include_echo=include_echo)

    app = FastAPI(title="atelier", version=__version__)
    app.state.settings = settings
    app.state.lineage_manager = lineages
    app.state.graph_store = lineages.graph_store
    app.state.media_store = lineages.media_store
    app.state.backend_registry = registry

    def sync_active_stores() -> None:
        app.state.graph_store = lineages.graph_store
        app.state.media_store = lineages.media_store
        app.state.job_queue.bind_stores(lineages.graph_store, lineages.media_store)

    app.state.sync_active_stores = sync_active_stores

    def on_job_complete() -> None:
        try:
            lineages.touch()
        except Exception:
            pass
        sync_active_stores()

    app.state.job_queue = JobQueue(
        registry=registry,
        graph=lineages.graph_store,
        media=lineages.media_store,
        on_complete=on_job_complete,
    )

    app.include_router(build_api_router())

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        ico = STATIC_DIR / "favicon.ico"
        if not ico.is_file():
            ico = STATIC_DIR / "icons" / "favicon.ico"
        return FileResponse(ico, media_type="image/x-icon")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        index_path = STATIC_DIR / "index.html"
        if index_path.is_file():
            return index_path.read_text(encoding="utf-8")
        return (
            "<!DOCTYPE html><html><head><title>atelier</title></head>"
            "<body><h1>atelier</h1><p>ok</p></body></html>"
        )

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
