"""Placeholder backends. Real implementations land in later phases."""

from __future__ import annotations

from typing import Any

from atelier.backends.base import Backend
from atelier.backends.registry import BackendRegistry
from atelier.backends.types import (
    BackendCapabilities,
    GeneratedAsset,
    GenerateMode,
    GenerationError,
    MediaInput,
)
from atelier.config import Settings

# Minimal 1x1 PNG
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class GrokBackend(Backend):
    """xAI Grok Imagine — implemented in phase 3."""

    name = "grok"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=True,
            supports_i2v=True,
        )

    def availability(self) -> tuple[bool, str | None]:
        if not self._settings.xai_api_key:
            return False, "XAI_API_KEY is not set"
        return True, None

    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        raise GenerationError("Grok backend not implemented yet (phase 3)")


class SDWebUIBackend(Backend):
    """A1111-compatible SD WebUI — implemented in phase 8."""

    name = "sd_webui"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=False,
            supports_i2v=False,
        )

    def availability(self) -> tuple[bool, str | None]:
        # Real probe in phase 8; for now always "configured" (URL present)
        if not self._settings.sd_webui_url:
            return False, "SD_WEBUI_URL is not set"
        return True, None

    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        raise GenerationError("SD WebUI backend not implemented yet (phase 8)")


class EchoBackend(Backend):
    """Test/dev backend: returns a tiny PNG (or echoes first input for i2i)."""

    name = "echo"

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=False,
            supports_i2v=False,
        )

    def availability(self) -> tuple[bool, str | None]:
        return True, None

    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        if mode == GenerateMode.i2i and inputs:
            src = inputs[0]
            return [
                GeneratedAsset(
                    data=src.data,
                    mime=src.mime,
                    params={"echo": True, "prompt": prompt, **params},
                )
            ]
        return [
            GeneratedAsset(
                data=_TINY_PNG,
                mime="image/png",
                params={"echo": True, "prompt": prompt, **params},
            )
        ]


def build_default_registry(settings: Settings, *, include_echo: bool = False) -> BackendRegistry:
    registry = BackendRegistry()
    registry.register(GrokBackend(settings))
    registry.register(SDWebUIBackend(settings))
    if include_echo:
        registry.register(EchoBackend())
    return registry
