"""Generate job pipeline: resolve inputs → backend → store → graph."""

from __future__ import annotations

from atelier.backends.registry import BackendRegistry
from atelier.backends.types import (
    BackendUnavailableError,
    GenerateMode,
    GenerateRequest,
    GenerationError,
    InvalidRequestError,
    MediaInput,
    MediaNotFoundError,
    ModeNotSupportedError,
)
from atelier.graph.models import MediaKind, MediaNode
from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore

_MODES_NEED_MEDIA_INPUT = frozenset({GenerateMode.i2i, GenerateMode.i2v})
_MODES_OUTPUT_VIDEO = frozenset({GenerateMode.t2v, GenerateMode.i2v})


def _validate_request(request: GenerateRequest, inputs: list[MediaInput]) -> None:
    if request.mode in _MODES_NEED_MEDIA_INPUT and not inputs:
        raise InvalidRequestError(f"mode {request.mode.value} requires at least one media input")

    if request.mode in (GenerateMode.t2i, GenerateMode.t2v) and not request.prompt.strip():
        raise InvalidRequestError(f"mode {request.mode.value} requires a non-empty prompt")

    if request.mode == GenerateMode.i2i:
        for inp in inputs:
            if inp.kind != MediaKind.image:
                raise InvalidRequestError(f"mode i2i expects image inputs only; got {inp.kind.value} ({inp.id})")
    elif request.mode == GenerateMode.i2v:
        # Image→video (animate) or video→video (edit). No pure text.
        ok = any(inp.kind in (MediaKind.image, MediaKind.video) for inp in inputs)
        if not ok:
            raise InvalidRequestError("mode i2v expects image or video inputs")


async def run_generate(
    request: GenerateRequest,
    *,
    registry: BackendRegistry,
    graph: GraphStore,
    media: MediaStore,
) -> list[MediaNode]:
    """Execute a generation job and return newly created MediaNodes."""
    backend = registry.get(request.backend)

    available, reason = backend.availability()
    if not available:
        raise BackendUnavailableError(backend.name, reason)

    caps = backend.capabilities()
    if not caps.supports(request.mode):
        raise ModeNotSupportedError(backend.name, request.mode)

    inputs: list[MediaInput] = []
    for mid in request.media_ids:
        node = graph.get_node(mid)
        if node is None:
            raise MediaNotFoundError(mid)
        inputs.append(
            MediaInput(
                id=node.id,
                kind=node.kind,
                mime=node.mime,
                data=media.read_bytes(node),
            )
        )

    _validate_request(request, inputs)

    try:
        assets = await backend.generate(
            mode=request.mode,
            prompt=request.prompt,
            inputs=inputs,
            params=dict(request.params),
        )
    except GenerationError:
        raise
    except Exception as e:
        raise GenerationError(str(e)) from e

    if not assets:
        raise GenerationError("backend returned no assets")

    parent_ids = list(request.media_ids)
    parent_roles = {pid: f"input{i + 1}" for i, pid in enumerate(parent_ids)}
    created: list[MediaNode] = []

    for asset in assets:
        # Soft check: video modes should return video mime
        if request.mode in _MODES_OUTPUT_VIDEO and not asset.mime.startswith("video/"):
            # allow backend to decide; still save as reported mime
            pass

        merged_params = {
            "mode": request.mode.value,
            **dict(request.params),
            **dict(asset.params),
        }
        node = media.save_bytes(
            asset.data,
            mime=asset.mime,
            backend=backend.name,
            prompt=request.prompt,
            params=merged_params,
            parent_ids=parent_ids,
        )
        graph.add_node(node, parent_roles=parent_roles)
        created.append(node)

    return created
