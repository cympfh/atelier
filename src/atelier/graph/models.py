"""Domain models for media nodes and the generation graph."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MediaKind(str, Enum):
    image = "image"
    video = "video"


class MediaNode(BaseModel):
    """A media asset: user upload or generation result."""

    id: str = Field(default_factory=new_id)
    kind: MediaKind
    # Relative path under data_dir/files/ (e.g. "{id}.png")
    filename: str
    mime: str
    created_at: datetime = Field(default_factory=utc_now)
    # "upload" | "grok" | "sd_webui" | ...
    backend: str | None = None
    prompt: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # Direct parent media ids (inputs). Edges also record this.
    parent_ids: list[str] = Field(default_factory=list)
    # Original upload name if any
    original_name: str | None = None


class Edge(BaseModel):
    """Directed dependency: source (input) -> target (output)."""

    id: str = Field(default_factory=new_id)
    source_id: str
    target_id: str
    # Optional role label, e.g. "image1", "init_image"
    role: str | None = None


class Graph(BaseModel):
    """In-memory / JSON-serializable generation graph."""

    nodes: dict[str, MediaNode] = Field(default_factory=dict)
    edges: list[Edge] = Field(default_factory=list)

    def get(self, node_id: str) -> MediaNode | None:
        return self.nodes.get(node_id)

    def add_node(self, node: MediaNode, *, parent_roles: dict[str, str] | None = None) -> MediaNode:
        """Insert node and edges from parent_ids.

        parent_roles maps parent_id -> role label.
        """
        self.nodes[node.id] = node
        roles = parent_roles or {}
        for parent_id in node.parent_ids:
            self.edges.append(
                Edge(
                    source_id=parent_id,
                    target_id=node.id,
                    role=roles.get(parent_id),
                )
            )
        return node

    def list_nodes(self) -> list[MediaNode]:
        return sorted(self.nodes.values(), key=lambda n: n.created_at, reverse=True)

    def is_leaf(self, node_id: str) -> bool:
        """True if no other node was generated from this one (no outgoing edges)."""
        if node_id not in self.nodes:
            return False
        return not any(e.source_id == node_id for e in self.edges)

    def children_of(self, node_id: str) -> list[str]:
        return [e.target_id for e in self.edges if e.source_id == node_id]

    def remove_node(self, node_id: str) -> MediaNode | None:
        """Remove node and edges that reference it. Caller must ensure leaf (or force)."""
        node = self.nodes.pop(node_id, None)
        if node is None:
            return None
        self.edges = [e for e in self.edges if e.source_id != node_id and e.target_id != node_id]
        return node
