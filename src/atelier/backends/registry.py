"""Named backend registry."""

from __future__ import annotations

from typing import Any

from atelier.backends.base import Backend
from atelier.backends.types import BackendInfo, BackendNotFoundError
from atelier.config import Settings


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

    def list_detail(self) -> list[dict[str, Any]]:
        """Info + optional param_schema for UI."""
        out: list[dict[str, Any]] = []
        for b in self._backends.values():
            info = b.info().model_dump()
            schema = getattr(b, "param_schema", None)
            if callable(schema):
                info["param_schema"] = schema()
            out.append(info)
        return out

    def __contains__(self, name: str) -> bool:
        return name in self._backends


def build_default_registry(settings: Settings, *, include_echo: bool = False) -> BackendRegistry:
    from atelier.backends.echo import EchoBackend
    from atelier.backends.grok import GrokBackend
    from atelier.backends.sd_webui import SDWebUIBackend

    registry = BackendRegistry()
    registry.register(GrokBackend(settings))
    registry.register(SDWebUIBackend(settings))
    if include_echo or settings.include_echo_backend:
        registry.register(EchoBackend())
    return registry
