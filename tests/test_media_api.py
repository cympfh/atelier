"""Phase 1: media store, graph persistence, upload API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atelier.app import create_app
from atelier.config import Settings
from atelier.graph.models import MediaKind
from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    settings = Settings(ATELIER_DATA_DIR=data_dir)
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_media_store_save_and_read(data_dir: Path) -> None:
    store = MediaStore(data_dir)
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    node = store.save_bytes(png_header, mime="image/png", backend="upload", original_name="x.png")
    assert node.kind == MediaKind.image
    assert node.filename.endswith(".png")
    assert store.path_for_node(node).is_file()
    assert store.read_bytes(node) == png_header


def test_graph_persist_roundtrip(data_dir: Path) -> None:
    store = MediaStore(data_dir)
    graph = GraphStore(data_dir)
    node = store.save_bytes(b"fake-image", mime="image/jpeg", backend="upload")
    graph.add_node(node)

    graph2 = GraphStore(data_dir)
    loaded = graph2.get_node(node.id)
    assert loaded is not None
    assert loaded.mime == "image/jpeg"
    assert loaded.backend == "upload"


def test_upload_list_get_file(client: TestClient) -> None:
    files = {"file": ("hello.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")}
    r = client.post("/api/media/upload", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    node_id = body["id"]
    assert body["kind"] == "image"
    assert body["backend"] == "upload"
    assert body["original_name"] == "hello.png"

    r = client.get("/api/media")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == node_id

    r = client.get(f"/api/media/{node_id}")
    assert r.status_code == 200
    assert r.json()["id"] == node_id

    r = client.get(f"/api/media/{node_id}/file")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")

    r = client.get("/api/media/does-not-exist")
    assert r.status_code == 404


def test_upload_rejects_empty(client: TestClient) -> None:
    r = client.post("/api/media/upload", files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 400


def test_upload_rejects_unsupported(client: TestClient) -> None:
    r = client.post("/api/media/upload", files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400


def test_delete_leaf_ok(client: TestClient) -> None:
    up = client.post(
        "/api/media/upload",
        files={"file": ("a.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")},
    )
    mid = up.json()["id"]
    r = client.delete(f"/api/media/{mid}")
    assert r.status_code == 204
    assert client.get(f"/api/media/{mid}").status_code == 404


def test_delete_non_leaf_conflict(data_dir: Path) -> None:
    # Use lineage-style layout via app with graph child edge
    settings = Settings(ATELIER_DATA_DIR=data_dir, ATELIER_ECHO=True)
    app = create_app(settings, include_echo=True)
    with TestClient(app) as client:
        up = client.post(
            "/api/media/upload",
            files={"file": ("p.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")},
        )
        parent_id = up.json()["id"]
        gen = client.post(
            "/api/generate",
            json={
                "mode": "i2i",
                "backend": "echo",
                "prompt": "child",
                "media_ids": [parent_id],
            },
        )
        assert gen.status_code == 200, gen.text
        r = client.delete(f"/api/media/{parent_id}")
        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "not_a_leaf"
        child_id = gen.json()["nodes"][0]["id"]
        assert client.delete(f"/api/media/{child_id}").status_code == 204
        assert client.delete(f"/api/media/{parent_id}").status_code == 204
