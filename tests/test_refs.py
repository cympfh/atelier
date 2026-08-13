"""@ImageN / @VideoN parsing."""

from __future__ import annotations

import pytest

from atelier.backends.types import InvalidRequestError
from atelier.graph.models import MediaKind, MediaNode
from atelier.refs import parse_refs, resolve_media_ids, strip_refs


def test_parse_refs_order_and_dedupe() -> None:
    refs = parse_refs("use @Image2 and @Image1 then @Image2 again @Video1")
    assert [(r.kind, r.index) for r in refs] == [
        (MediaKind.image, 2),
        (MediaKind.image, 1),
        (MediaKind.video, 1),
    ]


def test_strip_refs() -> None:
    assert strip_refs("hello @Image1 world") == "hello world"


def test_resolve_slots() -> None:
    prompt, ids = resolve_media_ids("edit @Image1 with @Image2", slot_ids=["aaa", "bbb"])
    assert ids == ["aaa", "bbb"]
    # Original prompt (with @refs) is preserved for node storage / Restore setup
    assert prompt == "edit @Image1 with @Image2"
    assert strip_refs(prompt) == "edit with"


def test_resolve_slots_oob() -> None:
    with pytest.raises(InvalidRequestError):
        resolve_media_ids("@Image3", slot_ids=["a"])


def test_resolve_candidates() -> None:
    nodes = [
        MediaNode(id="i1", kind=MediaKind.image, filename="a.png", mime="image/png"),
        MediaNode(id="v1", kind=MediaKind.video, filename="a.mp4", mime="video/mp4"),
        MediaNode(id="i2", kind=MediaKind.image, filename="b.png", mime="image/png"),
    ]
    prompt, ids = resolve_media_ids("mix @Image2 and @Video1", candidates=nodes)
    assert ids == ["i2", "v1"]
    assert prompt == "mix @Image2 and @Video1"
