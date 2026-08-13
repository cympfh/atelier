"""Load tagskeeper-compatible tags.toml for prompt suggest."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def load_tags_catalog(path: Path) -> dict[str, Any]:
    """Parse a tags.toml into groups + flat tag lists for autocomplete.

    Expected shape (tagskeeper):
      [group_name]
      default = true|false
      positive = ["tag", ...]
      negative = ["tag", ...]
    """
    path = Path(path).expanduser()
    with path.open("rb") as f:
        raw = tomllib.load(f)

    groups: list[dict[str, Any]] = []
    positive: list[str] = []
    negative: list[str] = []

    for name, body in raw.items():
        if not isinstance(body, dict):
            continue
        pos = [str(t) for t in (body.get("positive") or []) if t is not None and str(t).strip()]
        neg = [str(t) for t in (body.get("negative") or []) if t is not None and str(t).strip()]
        groups.append(
            {
                "name": str(name),
                "default": bool(body.get("default", False)),
                "positive": pos,
                "negative": neg,
            }
        )
        positive.extend(pos)
        negative.extend(neg)

    # preserve order, unique
    def uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for t in items:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    return {
        "path": str(path.resolve()),
        "groups": groups,
        "tags": uniq(positive),
        "negative_tags": uniq(negative),
    }
