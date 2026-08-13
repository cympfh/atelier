"""Grok client / backend with mocked HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx
import pytest

from atelier.backends.grok import GrokBackend
from atelier.backends.grok_client import GrokClient
from atelier.backends.types import GenerateMode, MediaInput
from atelier.config import Settings
from atelier.graph.models import MediaKind

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MockTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = None
        try:
            raw = await request.aread()
        except Exception:
            raw = b""
        if raw:
            try:
                body = json.loads(raw.decode())
            except Exception:
                body = raw
        self.calls.append((request.method, str(request.url), body))
        path = request.url.path

        if path.endswith("/images/generations"):
            b64 = base64.b64encode(_TINY_PNG).decode()
            return httpx.Response(200, json={"data": [{"b64_json": b64}]})
        if path.endswith("/images/edits"):
            b64 = base64.b64encode(_TINY_PNG).decode()
            return httpx.Response(200, json={"data": [{"b64_json": b64}]})
        if path.rstrip("/").endswith("/files") and request.method == "POST":
            return httpx.Response(200, json={"id": "file_test123", "filename": "source.mp4"})
        if "/files/" in path and request.method == "DELETE":
            return httpx.Response(200, json={"id": "file_test123", "deleted": True})
        if path.endswith("/videos/generations") or path.endswith("/videos/edits"):
            return httpx.Response(200, json={"request_id": "vid123"})
        if "/videos/vid123" in path:
            return httpx.Response(
                200,
                json={
                    "status": "done",
                    "video": {"url": "https://cdn.example/v.mp4", "respect_moderation": True},
                },
            )
        if path.endswith("/v.mp4") or "cdn.example" in str(request.url):
            return httpx.Response(200, content=b"fake-mp4", headers={"content-type": "video/mp4"})
        return httpx.Response(404, json={"error": "not found", "path": path})


def test_grok_unavailable_without_key() -> None:
    b = GrokBackend(Settings(XAI_API_KEY=None))
    ok, reason = b.availability()
    assert ok is False
    assert reason is not None


def test_grok_t2i_mock() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport))
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)

    assets = asyncio.run(backend.generate(GenerateMode.t2i, "cat", [], {"aspect_ratio": "1:1", "n": 1}))
    assert len(assets) == 1
    assert assets[0].mime.startswith("image/")
    assert assets[0].data.startswith(b"\x89PNG")
    assert any(c[1].endswith("/images/generations") for c in transport.calls)


def test_grok_i2i_mock() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport))
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    inp = MediaInput(id="a", kind=MediaKind.image, mime="image/png", data=_TINY_PNG)
    assets = asyncio.run(backend.generate(GenerateMode.i2i, "sketch", [inp], {}))
    assert len(assets) == 1
    assert any("/images/edits" in c[1] for c in transport.calls)
    body = next(c[2] for c in transport.calls if c[0] == "POST" and "/images/edits" in c[1])
    # single image: {url, type} map (bare string → 422)
    assert isinstance(body["image"], dict)
    assert body["image"]["type"] == "image_url"
    assert body["image"]["url"].startswith("data:image/png;base64,")


def test_grok_i2i_multi_image_payload() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport))
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    inputs = [
        MediaInput(id="a", kind=MediaKind.image, mime="image/png", data=_TINY_PNG),
        MediaInput(id="b", kind=MediaKind.image, mime="image/png", data=_TINY_PNG),
    ]
    assets = asyncio.run(backend.generate(GenerateMode.i2i, "combine", inputs, {}))
    assert len(assets) == 1
    body = next(c[2] for c in transport.calls if c[0] == "POST" and "/images/edits" in c[1])
    # multi: "images" array of {url, type} objects (mutually exclusive with "image")
    assert "image" not in body or body.get("image") is None
    assert isinstance(body["images"], list)
    assert len(body["images"]) == 2
    assert all(isinstance(o, dict) and o.get("type") == "image_url" for o in body["images"])
    assert all(o["url"].startswith("data:") for o in body["images"])
    # prompt should reference <IMAGE_0>, <IMAGE_1>
    assert "<IMAGE_0>" in body["prompt"]
    assert "<IMAGE_1>" in body["prompt"]


def test_grok_i2v_poll_mock() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport), video_timeout=30)
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    inp = MediaInput(id="a", kind=MediaKind.image, mime="image/png", data=_TINY_PNG)
    assets = asyncio.run(backend.generate(GenerateMode.i2v, "animate", [inp], {"duration": 5}))
    assert len(assets) == 1
    assert assets[0].mime == "video/mp4"
    assert assets[0].data == b"fake-mp4"


def test_grok_video_edit_from_video_input() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport), video_timeout=30)
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    vid = MediaInput(id="v1", kind=MediaKind.video, mime="video/mp4", data=b"fake-mp4-src")
    assets = asyncio.run(backend.generate(GenerateMode.v2v, "add a hat", [vid], {"n": 1}))
    assert len(assets) == 1
    # Upload source via Files API then edit with file_id
    uploads = [c for c in transport.calls if c[0] == "POST" and c[1].rstrip("/").endswith("/files")]
    assert len(uploads) >= 1
    gens = [c for c in transport.calls if c[0] == "POST" and "/videos/edits" in c[1]]
    assert len(gens) == 1
    assert not any("/videos/generations" in c[1] and c[0] == "POST" for c in transport.calls)
    body = gens[0][2]
    assert body["video"] == {"file_id": "file_test123"}
    assert body.get("model") == "grok-imagine-video"
    assert assets[0].params.get("edit_video") is True
    assert assets[0].params.get("model") == "grok-imagine-video"


def test_grok_video_n_serial() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport), video_timeout=30)
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    assets = asyncio.run(backend.generate(GenerateMode.t2v, "clip", [], {"n": 3, "duration": 5}))
    assert len(assets) == 3
    gens = [c for c in transport.calls if c[0] == "POST" and "/videos/generations" in c[1]]
    assert len(gens) == 3
    assert [a.params.get("index") for a in assets] == [0, 1, 2]
