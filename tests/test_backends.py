"""Backend registry and generate pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from atelier.backends import (
    BackendRegistry,
    EchoBackend,
    GenerateMode,
    GenerateRequest,
    GrokBackend,
    SDWebUIBackend,
    build_default_registry,
    run_generate,
)
from atelier.backends.types import (
    BackendNotFoundError,
    BackendUnavailableError,
    InvalidRequestError,
    MediaNotFoundError,
    ModeNotSupportedError,
)
from atelier.config import Settings
from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def stores(data_dir: Path) -> tuple[MediaStore, GraphStore, BackendRegistry]:
    media = MediaStore(data_dir)
    graph = GraphStore(data_dir)
    registry = BackendRegistry()
    registry.register(EchoBackend())
    return media, graph, registry


def test_registry_list_and_get() -> None:
    settings = Settings(XAI_API_KEY=None)
    reg = build_default_registry(settings, include_echo=True)
    names = set(reg.names())
    assert names == {"grok", "sd_webui", "echo"}
    infos = {i.name: i for i in reg.list_info()}
    assert infos["grok"].available is False
    assert infos["echo"].available is True


def test_grok_available_with_key() -> None:
    b = GrokBackend(Settings(XAI_API_KEY="test-key"))
    ok, reason = b.availability()
    assert ok is True
    assert reason is None


def test_pipeline_t2i(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    nodes = asyncio.run(
        run_generate(
            GenerateRequest(mode=GenerateMode.t2i, backend="echo", prompt="a cat"),
            registry=registry,
            graph=graph,
            media=media,
        )
    )
    assert len(nodes) == 1
    assert nodes[0].backend == "echo"
    assert nodes[0].params.get("mode") == "t2i"


def test_pipeline_i2i(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    src = media.save_bytes(b"source-bytes", mime="image/png", backend="upload")
    graph.add_node(src)
    nodes = asyncio.run(
        run_generate(
            GenerateRequest(
                mode=GenerateMode.i2i,
                backend="echo",
                prompt="edit me",
                media_ids=[src.id],
            ),
            registry=registry,
            graph=graph,
            media=media,
        )
    )
    assert nodes[0].parent_ids == [src.id]
    assert media.read_bytes(nodes[0]) == b"source-bytes"


def test_pipeline_keeps_at_refs_on_node(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    """Node prompt keeps @ImageN; backend receives stripped text."""
    media, graph, registry = stores
    src = media.save_bytes(b"source-bytes", mime="image/png", backend="upload")
    graph.add_node(src)
    nodes = asyncio.run(
        run_generate(
            GenerateRequest(
                mode=GenerateMode.i2i,
                backend="echo",
                prompt="recolor @Image1 slightly",
                media_ids=[src.id],
            ),
            registry=registry,
            graph=graph,
            media=media,
        )
    )
    assert nodes[0].prompt == "recolor @Image1 slightly"
    # Echo echoes the backend-facing prompt into asset params
    assert nodes[0].params.get("prompt") == "recolor slightly"


def test_pipeline_missing_media(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    with pytest.raises(MediaNotFoundError):
        asyncio.run(
            run_generate(
                GenerateRequest(
                    mode=GenerateMode.i2i,
                    backend="echo",
                    prompt="x",
                    media_ids=["nope"],
                ),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_unknown_backend(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    with pytest.raises(BackendNotFoundError):
        asyncio.run(
            run_generate(
                GenerateRequest(mode=GenerateMode.t2i, backend="nope", prompt="x"),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_i2i_rejects_video(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    vid = media.save_bytes(b"fake-mp4", mime="video/mp4", backend="upload")
    graph.add_node(vid)
    with pytest.raises(InvalidRequestError, match="image inputs only"):
        asyncio.run(
            run_generate(
                GenerateRequest(
                    mode=GenerateMode.i2i,
                    backend="echo",
                    prompt="x",
                    media_ids=[vid.id],
                ),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_i2i_requires_input(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    with pytest.raises(InvalidRequestError):
        asyncio.run(
            run_generate(
                GenerateRequest(mode=GenerateMode.i2i, backend="echo", prompt="x"),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_t2i_requires_prompt(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    with pytest.raises(InvalidRequestError):
        asyncio.run(
            run_generate(
                GenerateRequest(mode=GenerateMode.t2i, backend="echo", prompt="  "),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_mode_not_supported(stores: tuple[MediaStore, GraphStore, BackendRegistry]) -> None:
    media, graph, registry = stores
    with pytest.raises(ModeNotSupportedError):
        asyncio.run(
            run_generate(
                GenerateRequest(mode=GenerateMode.t2v, backend="echo", prompt="clip"),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_pipeline_backend_unavailable(data_dir: Path) -> None:
    media = MediaStore(data_dir)
    graph = GraphStore(data_dir)
    registry = BackendRegistry()
    registry.register(GrokBackend(Settings(XAI_API_KEY=None)))
    with pytest.raises(BackendUnavailableError):
        asyncio.run(
            run_generate(
                GenerateRequest(mode=GenerateMode.t2i, backend="grok", prompt="x"),
                registry=registry,
                graph=graph,
                media=media,
            )
        )


def test_sd_capabilities() -> None:
    b = SDWebUIBackend(Settings(), probe_on_availability=False)
    caps = b.capabilities()
    assert caps.supports_t2i and caps.supports_i2i and not caps.supports_t2v
