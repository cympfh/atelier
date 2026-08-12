"""Named lineage workspaces."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atelier.app import create_app
from atelier.config import Settings
from atelier.lineage import LineageManager, auto_lineage_name


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(ATELIER_DATA_DIR=tmp_path / "data", ATELIER_ECHO=True)
    app = create_app(settings, include_echo=True)
    with TestClient(app) as c:
        yield c


def test_auto_name_format() -> None:
    name = auto_lineage_name()
    assert len(name) >= 15
    assert "_" in name


def test_manager_creates_default(tmp_path: Path) -> None:
    lm = LineageManager(tmp_path / "data")
    cur = lm.current()
    assert cur.name
    assert lm.graph_store is not None
    listed = lm.list_all()
    assert any(m.id == cur.id for m in listed)


def test_api_lineage_flow(client: TestClient) -> None:
    cur = client.get("/api/lineages/current")
    assert cur.status_code == 200
    first_id = cur.json()["id"]

    # upload into first lineage
    up = client.post(
        "/api/media/upload",
        files={"file": ("a.png", b"\x89PNG\r\n\x1a\nxxxx", "image/png")},
    )
    assert up.status_code == 201
    media_id = up.json()["id"]

    # create second lineage (empty)
    created = client.post("/api/lineages", json={})
    assert created.status_code == 201
    second = created.json()
    assert second["id"] != first_id

    media2 = client.get("/api/media")
    assert media2.status_code == 200
    assert media2.json() == []

    # switch back
    sw = client.post("/api/lineages/current", json={"id": first_id})
    assert sw.status_code == 200
    media1 = client.get("/api/media")
    assert any(m["id"] == media_id for m in media1.json())

    # rename
    ren = client.patch(f"/api/lineages/{first_id}", json={"name": "my-work"})
    assert ren.status_code == 200
    assert ren.json()["name"] == "my-work"

    # save
    sav = client.post("/api/lineages/current/save")
    assert sav.status_code == 200

    listed = client.get("/api/lineages")
    assert listed.status_code == 200
    names = {x["name"] for x in listed.json()}
    assert "my-work" in names
