"""Generation job types and structured errors."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from atelier.graph.models import MediaKind


class GenerateMode(str, Enum):
    t2i = "t2i"
    i2i = "i2i"
    t2v = "t2v"
    i2v = "i2v"


class MediaInput(BaseModel):
    """Resolved input media passed to a backend."""

    id: str
    kind: MediaKind
    mime: str
    data: bytes


class GeneratedAsset(BaseModel):
    """Raw bytes returned by a backend before local save."""

    data: bytes
    mime: str
    params: dict[str, Any] = Field(default_factory=dict)


class GenerateRequest(BaseModel):
    """Job request (after any UI / @ parsing)."""

    mode: GenerateMode
    backend: str
    prompt: str = ""
    # Already-resolved media ids (parents)
    media_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class BackendCapabilities(BaseModel):
    supports_t2i: bool = False
    supports_i2i: bool = False
    supports_t2v: bool = False
    supports_i2v: bool = False

    def supports(self, mode: GenerateMode) -> bool:
        return {
            GenerateMode.t2i: self.supports_t2i,
            GenerateMode.i2i: self.supports_i2i,
            GenerateMode.t2v: self.supports_t2v,
            GenerateMode.i2v: self.supports_i2v,
        }[mode]


class BackendInfo(BaseModel):
    """Public status for registry / API."""

    name: str
    available: bool
    reason: str | None = None
    capabilities: BackendCapabilities


class AtelierError(Exception):
    """Structured application error."""

    def __init__(self, message: str, *, code: str = "error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"error": self.code, "detail": self.message}


class BackendNotFoundError(AtelierError):
    def __init__(self, name: str) -> None:
        super().__init__(f"backend not found: {name}", code="backend_not_found")


class BackendUnavailableError(AtelierError):
    def __init__(self, name: str, reason: str | None = None) -> None:
        detail = f"backend unavailable: {name}"
        if reason:
            detail = f"{detail} ({reason})"
        super().__init__(detail, code="backend_unavailable")


class ModeNotSupportedError(AtelierError):
    def __init__(self, name: str, mode: GenerateMode) -> None:
        super().__init__(
            f"backend {name} does not support mode {mode.value}",
            code="mode_not_supported",
        )


class MediaNotFoundError(AtelierError):
    def __init__(self, node_id: str) -> None:
        super().__init__(f"media not found: {node_id}", code="media_not_found")


class InvalidRequestError(AtelierError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_request")


class GenerationError(AtelierError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="generation_failed")
