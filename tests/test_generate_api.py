"""Generate / backends / graph API."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atelier.app import create_app
from atelier.config import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(ATELIER_DATA_DIR=tmp_path / "data", ATELIER_ECHO=True, XAI_API_KEY=None)
    app = create_app(settings, include_echo=True)
    with TestClient(app) as c:
        yield c


def test_list_backends(client: TestClient) -> None:
    r = client.get("/api/backends")
    assert r.status_code == 200
    names = {b["name"] for b in r.json()}
    assert "echo" in names
    assert "grok" in names
    echo = next(b for b in r.json() if b["name"] == "echo")
    assert echo["available"] is True
    assert "param_schema" in echo


def test_generate_echo_t2i(client: TestClient) -> None:
    r = client.post(
        "/api/generate",
        json={"mode": "t2i", "backend": "echo", "prompt": "a rock"},
    )
    assert r.status_code == 200, r.text
    nodes = r.json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["backend"] == "echo"

    g = client.get("/api/graph")
    assert g.status_code == 200
    assert nodes[0]["id"] in g.json()["nodes"]


def test_generate_with_at_ref(client: TestClient) -> None:
    up = client.post(
        "/api/media/upload",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")},
    )
    assert up.status_code == 201
    mid = up.json()["id"]
    r = client.post(
        "/api/generate",
        json={
            "mode": "i2i",
            "backend": "echo",
            "prompt": "recolor @Image1",
            "media_ids": [mid],
            "input_slots": [mid],
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()["nodes"][0]
    assert out["parent_ids"] == [mid]
    assert "@Image" not in (out.get("prompt") or "")


def test_generate_unavailable_grok(client: TestClient) -> None:
    r = client.post(
        "/api/generate",
        json={"mode": "t2i", "backend": "grok", "prompt": "x"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "backend_unavailable"


def test_generate_invalid_mode_echo(client: TestClient) -> None:
    r = client.post(
        "/api/generate",
        json={"mode": "t2v", "backend": "echo", "prompt": "x"},
    )
    assert r.status_code == 400
