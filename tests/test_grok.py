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
        if request.content:
            try:
                body = json.loads(request.content.decode())
            except Exception:
                body = request.content
        self.calls.append((request.method, str(request.url), body))
        path = request.url.path

        if path.endswith("/images/generations"):
            b64 = base64.b64encode(_TINY_PNG).decode()
            return httpx.Response(200, json={"data": [{"b64_json": b64}]})
        if path.endswith("/images/edits"):
            b64 = base64.b64encode(_TINY_PNG).decode()
            return httpx.Response(200, json={"data": [{"b64_json": b64}]})
        if path.endswith("/videos/generations"):
            return httpx.Response(200, json={"request_id": "vid123"})
        if "/videos/vid123" in path:
            return httpx.Response(
                200,
                json={"status": "done", "video": {"url": "https://cdn.example/v.mp4"}},
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


def test_grok_i2v_poll_mock() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport), video_timeout=30)
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    inp = MediaInput(id="a", kind=MediaKind.image, mime="image/png", data=_TINY_PNG)
    assets = asyncio.run(backend.generate(GenerateMode.i2v, "animate", [inp], {"duration": 5}))
    assert len(assets) == 1
    assert assets[0].mime == "video/mp4"
    assert assets[0].data == b"fake-mp4"


def test_grok_video_n_serial() -> None:
    transport = MockTransport()
    client = GrokClient("key", client=httpx.AsyncClient(transport=transport), video_timeout=30)
    backend = GrokBackend(Settings(XAI_API_KEY="key"), client=client)
    assets = asyncio.run(backend.generate(GenerateMode.t2v, "clip", [], {"n": 3, "duration": 5}))
    assert len(assets) == 3
    gens = [c for c in transport.calls if c[0] == "POST" and "/videos/generations" in c[1]]
    assert len(gens) == 3
    assert [a.params.get("index") for a in assets] == [0, 1, 2]
