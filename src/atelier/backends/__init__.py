"""Generation backends (Grok, SD WebUI, ...)."""

from atelier.backends.base import Backend
from atelier.backends.pipeline import run_generate
from atelier.backends.registry import BackendRegistry
from atelier.backends.stubs import EchoBackend, GrokBackend, SDWebUIBackend, build_default_registry
from atelier.backends.types import (
    AtelierError,
    BackendCapabilities,
    BackendInfo,
    GenerateMode,
    GenerateRequest,
    GeneratedAsset,
    MediaInput,
)

__all__ = [
    "AtelierError",
    "Backend",
    "BackendCapabilities",
    "BackendInfo",
    "BackendRegistry",
    "EchoBackend",
    "GenerateMode",
    "GenerateRequest",
    "GeneratedAsset",
    "GrokBackend",
    "MediaInput",
    "SDWebUIBackend",
    "build_default_registry",
    "run_generate",
]
