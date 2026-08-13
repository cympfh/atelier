"""Tag catalog loading and API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from atelier.app import create_app
from atelier.config import Settings
from atelier.tags import load_tags_catalog

_SAMPLE = """
[template]
default = true
positive = ["score_9", "masterpiece"]
negative = ["lowres", "bad quality"]

[1girl]
default = false
positive = ["1girl", "solo"]
negative = []
"""


def test_load_tags_catalog(tmp_path: Path) -> None:
    p = tmp_path / "tags.toml"
    p.write_text(_SAMPLE, encoding="utf-8")
    cat = load_tags_catalog(p)
    assert len(cat["groups"]) == 2
    assert "score_9" in cat["tags"]
    assert "lowres" in cat["negative_tags"]
    names = [g["name"] for g in cat["groups"]]
    assert names == ["template", "1girl"]


def test_api_tags(tmp_path: Path) -> None:
    p = tmp_path / "tags.toml"
    p.write_text(_SAMPLE, encoding="utf-8")
    app = create_app(Settings(ATELIER_TAGS_TOML=str(p), ATELIER_DATA_DIR=str(tmp_path / "data")))
    client = TestClient(app)
    r = client.get("/api/tags")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert "masterpiece" in data["tags"]


def test_api_tags_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.toml"
    app = create_app(Settings(ATELIER_TAGS_TOML=str(missing), ATELIER_DATA_DIR=str(tmp_path / "data")))
    client = TestClient(app)
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert r.json()["available"] is False
