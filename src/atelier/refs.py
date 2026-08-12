"""@ImageN / @VideoN prompt reference parsing and resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass

from atelier.backends.types import InvalidRequestError
from atelier.graph.models import MediaKind, MediaNode

# @Image1, @image2, @Video3
REF_PATTERN = re.compile(r"@(Image|Video)(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class MediaRef:
    kind: MediaKind
    index: int  # 1-based
    raw: str


def parse_refs(prompt: str) -> list[MediaRef]:
    """Extract unique refs in order of first appearance."""
    seen: set[tuple[MediaKind, int]] = set()
    out: list[MediaRef] = []
    for m in REF_PATTERN.finditer(prompt):
        kind = MediaKind.image if m.group(1).lower() == "image" else MediaKind.video
        index = int(m.group(2))
        key = (kind, index)
        if key in seen:
            continue
        seen.add(key)
        out.append(MediaRef(kind=kind, index=index, raw=m.group(0)))
    return out


def strip_refs(prompt: str) -> str:
    """Remove @ImageN/@VideoN tokens (collapse leftover spaces)."""
    cleaned = REF_PATTERN.sub(" ", prompt)
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_media_ids(
    prompt: str,
    *,
    slot_ids: list[str] | None = None,
    candidates: list[MediaNode] | None = None,
) -> tuple[str, list[str]]:
    """Resolve @refs to media ids.

    Rules:
    1. If slot_ids provided: @Image1 -> slot_ids[0], @Image2 -> slot_ids[1], ...
       (Video refs also map by index into the same slot list when kind matches,
        or into the same positional slots for simplicity).
    2. Else if candidates provided: Nth image/video among candidates (newest-first list ok).
    3. Explicit media_ids on the request still merge separately in the API layer.

    Returns (cleaned_prompt, resolved_ids in ref order).
    """
    refs = parse_refs(prompt)
    if not refs:
        return prompt, []

    resolved: list[str] = []

    if slot_ids is not None:
        for ref in refs:
            idx = ref.index - 1
            if idx < 0 or idx >= len(slot_ids):
                raise InvalidRequestError(f"{ref.raw} out of range (have {len(slot_ids)} input slot(s))")
            mid = slot_ids[idx]
            if mid not in resolved:
                resolved.append(mid)
        return strip_refs(prompt), resolved

    if candidates is None:
        raise InvalidRequestError("cannot resolve @refs without input slots or candidates")

    images = [n for n in candidates if n.kind == MediaKind.image]
    videos = [n for n in candidates if n.kind == MediaKind.video]

    for ref in refs:
        pool = images if ref.kind == MediaKind.image else videos
        idx = ref.index - 1
        if idx < 0 or idx >= len(pool):
            raise InvalidRequestError(f"{ref.raw} not found (have {len(pool)} {ref.kind.value}(s))")
        mid = pool[idx].id
        if mid not in resolved:
            resolved.append(mid)

    return strip_refs(prompt), resolved
