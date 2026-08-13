"""SD WebUI backend with mocked HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from typing import Any

import httpx
import pytest

from atelier.backends.sd_webui import SDWebUIBackend, apply_loras_to_prompt, parse_lora_tags
from atelier.backends.types import GenerateMode, MediaInput
from atelier.config import Settings
from atelier.graph.models import MediaKind

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class SDTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_body: dict[str, Any] | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(f"{request.method} {request.url.path}")
        path = request.url.path
        if path.endswith("/sdapi/v1/sd-models"):
            return httpx.Response(
                200,
                json=[{"title": "WAI-NSFW-illustrious-SDXL.safetensors", "model_name": "WAI"}],
            )
        if path.endswith("/sdapi/v1/options"):
            return httpx.Response(200, json={})
        if path.endswith("/sdapi/v1/txt2img") or path.endswith("/sdapi/v1/img2img"):
            body = json.loads(request.content.decode()) if request.content else {}
            self.last_body = body
            assert "prompt" in body
            b64 = base64.b64encode(_TINY_PNG).decode()
            return httpx.Response(200, json={"images": [b64]})
        return httpx.Response(404)


def test_parse_lora_tags() -> None:
    assert parse_lora_tags("foo:0.8, bar") == ["<lora:foo:0.8>", "<lora:bar:1.0>"]
    assert apply_loras_to_prompt("1girl", "style:0.7") == "1girl <lora:style:0.7>"


def test_sd_availability_cache_and_force(monkeypatch: pytest.MonkeyPatch) -> None:
    """Probe runs once; cache hits skip network; force= re-probes."""
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        probe_on_availability=True,
    )
    calls = {"n": 0}

    def fake_probe() -> tuple[bool, str | None]:
        calls["n"] += 1
        return True, None

    monkeypatch.setattr(backend, "_do_probe", fake_probe)
    assert backend.availability() == (True, None)
    assert backend.availability() == (True, None)
    assert calls["n"] == 1
    assert backend.availability(force=True) == (True, None)
    assert calls["n"] == 2


def test_sd_availability_stale_while_revalidate(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        probe_on_availability=True,
    )
    results = iter([(True, None), (False, "down")])
    done = threading.Event()
    calls = {"n": 0}

    def fake_probe() -> tuple[bool, str | None]:
        calls["n"] += 1
        out = next(results)
        if calls["n"] >= 2:
            done.set()
        return out

    monkeypatch.setattr(backend, "_do_probe", fake_probe)
    # First call populates cache
    assert backend.availability() == (True, None)
    # Expire cache
    backend._cache_at = time.monotonic() - 999.0
    # Stale hit returns old value immediately, schedules background probe
    assert backend.availability() == (True, None)
    assert done.wait(timeout=2.0)
    # After background probe finishes, next call sees new cache
    assert backend.availability() == (False, "down")


def test_sd_txt2img() -> None:
    transport = SDTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://sd.test")
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        client=client,
        probe_on_availability=False,
    )
    assets = asyncio.run(backend.generate(GenerateMode.t2i, "1girl", [], {"steps": 10}))
    assert len(assets) == 1
    assert assets[0].data.startswith(b"\x89PNG")
    assert any("txt2img" in c for c in transport.calls)


def test_sd_img2img() -> None:
    transport = SDTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://sd.test")
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        client=client,
        probe_on_availability=False,
    )
    inp = MediaInput(id="x", kind=MediaKind.image, mime="image/png", data=_TINY_PNG)
    assets = asyncio.run(backend.generate(GenerateMode.i2i, "edit", [inp], {"denoising_strength": 0.4}))
    assert len(assets) == 1
    assert any("img2img" in c for c in transport.calls)


def test_sd_list_models() -> None:
    transport = SDTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://sd.test")
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        client=client,
        probe_on_availability=False,
    )
    models = asyncio.run(backend.list_models())
    assert models[0]["title"].startswith("WAI")


def test_sd_lora_and_extensions_in_payload() -> None:
    transport = SDTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://sd.test")
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        client=client,
        probe_on_availability=False,
    )
    asyncio.run(
        backend.generate(
            GenerateMode.t2i,
            "1girl",
            [],
            {
                "lora": "detail:0.6",
                "clip_skip": 2,
                "enable_hr": True,
                "hr_scale": 1.5,
                "alwayson_scripts": {"ControlNet": {"args": []}},
            },
        )
    )
    body = transport.last_body
    assert body is not None
    assert "<lora:detail:0.6>" in body["prompt"]
    assert body["override_settings"]["CLIP_stop_at_last_layers"] == 2
    assert body["enable_hr"] is True
    assert body["alwayson_scripts"]["ControlNet"]["args"] == []


def test_sd_batch_n() -> None:
    transport = SDTransport()
    client = httpx.AsyncClient(transport=transport, base_url="http://sd.test")
    backend = SDWebUIBackend(
        Settings(SD_WEBUI_URL="http://sd.test"),
        client=client,
        probe_on_availability=False,
    )
    asyncio.run(backend.generate(GenerateMode.t2i, "1girl", [], {"n": 4}))
    assert transport.last_body is not None
    assert transport.last_body["batch_size"] == 4
    assert transport.last_body["n_iter"] == 1
