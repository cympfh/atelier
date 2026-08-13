"""Backend abstract base."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from atelier.backends.types import (
    BackendCapabilities,
    BackendInfo,
    GeneratedAsset,
    GenerateMode,
    MediaInput,
)


class Backend(ABC):
    """Image/video generation backend."""

    name: str

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        """Modes this backend implements."""

    @abstractmethod
    def availability(self, *, force: bool = False) -> tuple[bool, str | None]:
        """(available, reason_if_not). ``force`` re-probes even if cached."""

    def info(self) -> BackendInfo:
        available, reason = self.availability()
        return BackendInfo(
            name=self.name,
            available=available,
            reason=None if available else reason,
            capabilities=self.capabilities(),
        )

    @abstractmethod
    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        """Run generation. Raise GenerationError on failure."""
