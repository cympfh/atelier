"""Grok (xAI Imagine) backend implementation."""

from __future__ import annotations

from typing import Any

from atelier.backends.base import Backend
from atelier.backends.grok_client import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_VIDEO_MODEL,
    GrokClient,
    to_data_uri,
)
from atelier.backends.types import (
    BackendCapabilities,
    GeneratedAsset,
    GenerateMode,
    GenerationError,
    MediaInput,
)
from atelier.config import Settings

# Params exposed to UI / API
GROK_PARAM_SCHEMA: dict[str, Any] = {
    "aspect_ratio": {
        "type": "string",
        "enum": ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "2:1", "1:2"],
        "default": "1:1",
        "modes": ["t2i", "i2i", "t2v", "i2v"],
    },
    "n": {
        "type": "integer",
        "minimum": 1,
        "maximum": 10,
        "default": 1,
        "description": "Number of outputs (video: sequential requests)",
        "modes": ["t2i", "i2i", "t2v", "i2v"],
    },
    "image_model": {
        "type": "string",
        "default": DEFAULT_IMAGE_MODEL,
        "modes": ["t2i", "i2i"],
    },
    "video_model": {
        "type": "string",
        "default": DEFAULT_VIDEO_MODEL,
        "modes": ["t2v", "i2v"],
    },
    "duration": {
        "type": "integer",
        "minimum": 1,
        "maximum": 15,
        "default": 6,
        "modes": ["t2v", "i2v"],
    },
    "resolution": {
        "type": "string",
        "enum": ["480p", "720p"],
        "default": "480p",
        "modes": ["t2v", "i2v"],
    },
}


class GrokBackend(Backend):
    name = "grok"

    def __init__(self, settings: Settings, client: GrokClient | None = None) -> None:
        self._settings = settings
        self._client = client

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=True,
            supports_i2v=True,
        )

    def availability(self) -> tuple[bool, str | None]:
        if not self._settings.xai_api_key and self._client is None:
            return False, "XAI_API_KEY is not set"
        return True, None

    def param_schema(self) -> dict[str, Any]:
        return GROK_PARAM_SCHEMA

    def _client_or_create(self) -> GrokClient:
        if self._client is not None:
            return self._client
        key = self._settings.xai_api_key
        if not key:
            raise GenerationError("XAI_API_KEY is not set")
        return GrokClient(
            key,
            http_timeout=self._settings.http_timeout,
            video_timeout=self._settings.video_timeout,
        )

    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        client = self._client_or_create()
        try:
            if mode == GenerateMode.t2i:
                return await self._t2i(client, prompt, params)
            if mode == GenerateMode.i2i:
                return await self._i2i(client, prompt, inputs, params)
            if mode == GenerateMode.t2v:
                return await self._t2v(client, prompt, params)
            if mode == GenerateMode.i2v:
                return await self._i2v(client, prompt, inputs, params)
            raise GenerationError(f"unsupported mode: {mode}")
        finally:
            if self._client is None:
                await client.aclose()

    async def _t2i(self, client: GrokClient, prompt: str, params: dict[str, Any]) -> list[GeneratedAsset]:
        model = str(params.get("image_model") or params.get("model") or DEFAULT_IMAGE_MODEL)
        n = int(params.get("n") or 1)
        aspect = params.get("aspect_ratio")
        pairs = await client.generate_images(
            prompt,
            model=model,
            n=n,
            aspect_ratio=str(aspect) if aspect else None,
        )
        return [
            GeneratedAsset(data=data, mime=mime, params={"model": model, "n": n, "aspect_ratio": aspect})
            for data, mime in pairs
        ]

    async def _i2i(
        self,
        client: GrokClient,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        if not inputs:
            raise GenerationError("i2i requires image inputs")
        model = str(params.get("image_model") or params.get("model") or DEFAULT_IMAGE_MODEL)
        n = int(params.get("n") or 1)
        uris = [to_data_uri(i.data, i.mime) for i in inputs if i.mime.startswith("image/")]
        if not uris:
            raise GenerationError("i2i requires image/* inputs")
        pairs = await client.edit_images(prompt, uris, model=model, n=n)
        return [
            GeneratedAsset(
                data=data,
                mime=mime,
                params={"model": model, "n": n, "input_count": len(uris)},
            )
            for data, mime in pairs
        ]

    async def _t2v(self, client: GrokClient, prompt: str, params: dict[str, Any]) -> list[GeneratedAsset]:
        model = str(params.get("video_model") or params.get("model") or DEFAULT_VIDEO_MODEL)
        n = max(1, min(10, int(params.get("n") or 1)))
        duration = params.get("duration")
        aspect = params.get("aspect_ratio")
        resolution = params.get("resolution")
        out: list[GeneratedAsset] = []
        for i in range(n):
            data, mime = await client.generate_video(
                prompt,
                model=model,
                duration=int(duration) if duration is not None else None,
                aspect_ratio=str(aspect) if aspect else None,
                resolution=str(resolution) if resolution else None,
            )
            out.append(
                GeneratedAsset(
                    data=data,
                    mime=mime,
                    params={
                        "model": model,
                        "n": n,
                        "index": i,
                        "duration": duration,
                        "aspect_ratio": aspect,
                        "resolution": resolution,
                    },
                )
            )
        return out

    async def _i2v(
        self,
        client: GrokClient,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        """Image→video (animate) or video→video (edit) depending on input kind."""
        if not inputs:
            raise GenerationError("i2v requires an image or video input")

        video_in = next((i for i in inputs if i.mime.startswith("video/")), None)
        img = next((i for i in inputs if i.mime.startswith("image/")), None)
        if video_in is None and img is None:
            raise GenerationError("i2v requires an image/* or video/* input")

        model = str(params.get("video_model") or params.get("model") or DEFAULT_VIDEO_MODEL)
        n = max(1, min(10, int(params.get("n") or 1)))
        duration = params.get("duration")
        aspect = params.get("aspect_ratio")
        resolution = params.get("resolution")

        # Prefer explicit video edit when a video is among inputs
        if video_in is not None:
            uri = to_data_uri(video_in.data, video_in.mime)
            out: list[GeneratedAsset] = []
            for i in range(n):
                data, mime = await client.generate_video(
                    prompt,
                    model=model,
                    video_uri=uri,
                )
                out.append(
                    GeneratedAsset(
                        data=data,
                        mime=mime,
                        params={
                            "model": model,
                            "n": n,
                            "index": i,
                            "edit_video": True,
                            "source_id": video_in.id,
                        },
                    )
                )
            return out

        assert img is not None
        uri = to_data_uri(img.data, img.mime)
        out = []
        for i in range(n):
            data, mime = await client.generate_video(
                prompt,
                model=model,
                image_uri=uri,
                duration=int(duration) if duration is not None else None,
                aspect_ratio=str(aspect) if aspect else None,
                resolution=str(resolution) if resolution else None,
            )
            out.append(
                GeneratedAsset(
                    data=data,
                    mime=mime,
                    params={
                        "model": model,
                        "n": n,
                        "index": i,
                        "duration": duration,
                        "aspect_ratio": aspect,
                        "resolution": resolution,
                        "source_id": img.id,
                    },
                )
            )
        return out
