"""Phase 2: backend registry and generate pipeline."""

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
    assert infos["grok"].reason is not None
    assert infos["echo"].available is True
    assert infos["echo"].capabilities.supports_t2i is True


def test_grok_available_with_key() -> None:
    settings = Settings(XAI_API_KEY="test-key")
    b = GrokBackend(settings)
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
    node = nodes[0]
    assert node.backend == "echo"
    assert node.kind.value == "image"
    assert node.prompt == "a cat"
    assert node.params.get("mode") == "t2i"
    assert graph.get_node(node.id) is not None
    assert media.path_for_node(node).is_file()


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
    assert len(nodes) == 1
    out = nodes[0]
    assert out.parent_ids == [src.id]
    assert media.read_bytes(out) == b"source-bytes"
    snap = graph.snapshot()
    assert any(e.source_id == src.id and e.target_id == out.id for e in snap.edges)


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
    b = SDWebUIBackend(Settings())
    caps = b.capabilities()
    assert caps.supports_t2i
    assert caps.supports_i2i
    assert not caps.supports_t2v
