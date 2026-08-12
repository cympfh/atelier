"""SD WebUI backend with mocked HTTP."""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

import httpx

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
