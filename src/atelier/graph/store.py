"""JSON persistence for the generation graph."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from atelier.graph.models import Edge, Graph, MediaNode


class GraphStore:
    """Load/save Graph as data_dir/graph.json. Thread-safe for single process."""

    def __init__(self, data_dir: Path, filename: str = "graph.json") -> None:
        self.data_dir = data_dir
        self.path = data_dir / filename
        self._lock = threading.RLock()
        self._graph = Graph()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.load()

    @property
    def graph(self) -> Graph:
        return self._graph

    def load(self) -> Graph:
        with self._lock:
            if not self.path.is_file():
                self._graph = Graph()
                return self._graph
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._graph = Graph.model_validate(raw)
            return self._graph

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = self._graph.model_dump(mode="json")
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            tmp.replace(self.path)

    def get_node(self, node_id: str) -> MediaNode | None:
        with self._lock:
            return self._graph.get(node_id)

    def list_nodes(self) -> list[MediaNode]:
        with self._lock:
            return self._graph.list_nodes()

    def add_node(self, node: MediaNode, *, parent_roles: dict[str, str] | None = None) -> MediaNode:
        with self._lock:
            self._graph.add_node(node, parent_roles=parent_roles)
            self.save()
            return node

    def is_leaf(self, node_id: str) -> bool:
        with self._lock:
            return self._graph.is_leaf(node_id)

    def delete_leaf(self, node_id: str) -> MediaNode:
        """Delete a leaf node. Raises KeyError if missing, ValueError if not a leaf."""
        with self._lock:
            if self._graph.get(node_id) is None:
                raise KeyError(node_id)
            if not self._graph.is_leaf(node_id):
                kids = self._graph.children_of(node_id)
                raise ValueError(f"not a leaf; has children: {kids}")
            node = self._graph.remove_node(node_id)
            assert node is not None
            self.save()
            return node

    def snapshot(self) -> Graph:
        """Return a deep copy for API responses."""
        with self._lock:
            return Graph.model_validate(self._graph.model_dump(mode="json"))
