"""Named backend registry."""

from __future__ import annotations

from atelier.backends.base import Backend
from atelier.backends.types import BackendInfo, BackendNotFoundError


class BackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, Backend] = {}

    def register(self, backend: Backend) -> None:
        self._backends[backend.name] = backend

    def get(self, name: str) -> Backend:
        try:
            return self._backends[name]
        except KeyError as e:
            raise BackendNotFoundError(name) from e

    def names(self) -> list[str]:
        return list(self._backends.keys())

    def list_info(self) -> list[BackendInfo]:
        return [b.info() for b in self._backends.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._backends
