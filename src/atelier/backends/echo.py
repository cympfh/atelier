"""Echo backend for tests and offline UI demos."""

from __future__ import annotations

from typing import Any

from atelier.backends.base import Backend
from atelier.backends.types import (
    BackendCapabilities,
    GeneratedAsset,
    GenerateMode,
    MediaInput,
)

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

ECHO_PARAM_SCHEMA: dict[str, Any] = {
    "note": {"type": "string", "default": "", "modes": ["t2i", "i2i"]},
}


class EchoBackend(Backend):
    name = "echo"

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=False,
            supports_i2v=False,
        )

    def availability(self, *, force: bool = False) -> tuple[bool, str | None]:
        return True, None

    def param_schema(self) -> dict[str, Any]:
        return ECHO_PARAM_SCHEMA

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
