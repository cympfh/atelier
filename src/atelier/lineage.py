"""Named lineage workspaces (saved generation graphs + media)."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from atelier.graph.store import GraphStore
from atelier.media.store import MediaStore

_SAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def auto_lineage_name(when: datetime | None = None) -> str:
    dt = when or _utc_now()
    return dt.strftime("%Y-%m-%d_%H-%M-%S")


class LineageMeta(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class LineageManager:
    """Multiple lineages under data_dir/lineages/{id}/."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.root = data_dir / "lineages"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._active_id: str | None = None
        self._graph: GraphStore | None = None
        self._media: MediaStore | None = None
        self._ensure_active()

    @property
    def active_id(self) -> str:
        assert self._active_id is not None
        return self._active_id

    @property
    def graph_store(self) -> GraphStore:
        assert self._graph is not None
        return self._graph

    @property
    def media_store(self) -> MediaStore:
        assert self._media is not None
        return self._media

    def _lineage_dir(self, lineage_id: str) -> Path:
        return self.root / lineage_id

    def _meta_path(self, lineage_id: str) -> Path:
        return self._lineage_dir(lineage_id) / "meta.json"

    def _read_meta(self, lineage_id: str) -> LineageMeta | None:
        path = self._meta_path(lineage_id)
        if not path.is_file():
            return None
        return LineageMeta.model_validate_json(path.read_text(encoding="utf-8"))

    def _write_meta(self, meta: LineageMeta) -> None:
        path = self._meta_path(meta.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def _active_path(self) -> Path:
        return self.root / "active.json"

    def _save_active_pointer(self) -> None:
        path = self._active_path()
        path.write_text(json.dumps({"id": self._active_id}, indent=2) + "\n", encoding="utf-8")

    def _load_active_pointer(self) -> str | None:
        path = self._active_path()
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("id")
        except Exception:
            return None

    def list_all(self) -> list[LineageMeta]:
        with self._lock:
            items: list[LineageMeta] = []
            for child in self.root.iterdir():
                if not child.is_dir():
                    continue
                meta = self._read_meta(child.name)
                if meta:
                    items.append(meta)
            items.sort(key=lambda m: m.updated_at, reverse=True)
            return items

    def get(self, lineage_id: str) -> LineageMeta | None:
        with self._lock:
            return self._read_meta(lineage_id)

    def create(self, name: str | None = None) -> LineageMeta:
        with self._lock:
            now = _utc_now()
            lid = uuid4().hex
            meta = LineageMeta(
                id=lid,
                name=(name or auto_lineage_name(now)).strip() or auto_lineage_name(now),
                created_at=now,
                updated_at=now,
            )
            self._lineage_dir(lid).mkdir(parents=True, exist_ok=True)
            (self._lineage_dir(lid) / "files").mkdir(exist_ok=True)
            self._write_meta(meta)
            # empty graph
            GraphStore(self._lineage_dir(lid))
            return meta

    def rename(self, lineage_id: str, name: str) -> LineageMeta:
        with self._lock:
            meta = self._read_meta(lineage_id)
            if meta is None:
                raise KeyError(lineage_id)
            meta.name = name.strip() or meta.name
            meta.updated_at = _utc_now()
            self._write_meta(meta)
            return meta

    def touch(self, lineage_id: str | None = None) -> LineageMeta:
        with self._lock:
            lid = lineage_id or self._active_id
            if not lid:
                raise RuntimeError("no active lineage")
            meta = self._read_meta(lid)
            if meta is None:
                raise KeyError(lid)
            meta.updated_at = _utc_now()
            self._write_meta(meta)
            return meta

    def switch(self, lineage_id: str) -> LineageMeta:
        with self._lock:
            meta = self._read_meta(lineage_id)
            if meta is None:
                raise KeyError(lineage_id)
            self._bind(lineage_id)
            self._save_active_pointer()
            return meta

    def current(self) -> LineageMeta:
        with self._lock:
            meta = self._read_meta(self.active_id)
            if meta is None:
                raise RuntimeError("active lineage missing meta")
            return meta

    def save_now(self) -> LineageMeta:
        """Flush graph to disk and touch meta (autosave / explicit save)."""
        with self._lock:
            if self._graph is not None:
                self._graph.save()
            return self.touch()

    def _bind(self, lineage_id: str) -> None:
        path = self._lineage_dir(lineage_id)
        path.mkdir(parents=True, exist_ok=True)
        self._active_id = lineage_id
        self._graph = GraphStore(path)
        self._media = MediaStore(path)

    def _ensure_active(self) -> None:
        with self._lock:
            # Migrate legacy data_dir/graph.json + files/ into a lineage once
            self._maybe_migrate_legacy()

            pointer = self._load_active_pointer()
            if pointer and self._read_meta(pointer):
                self._bind(pointer)
                return

            existing = self.list_all()
            if existing:
                self._bind(existing[0].id)
                self._save_active_pointer()
                return

            meta = self.create(None)
            self._bind(meta.id)
            self._save_active_pointer()

    def _maybe_migrate_legacy(self) -> None:
        legacy_graph = self.data_dir / "graph.json"
        legacy_files = self.data_dir / "files"
        if not legacy_graph.is_file() and not (legacy_files.is_dir() and any(legacy_files.iterdir())):
            return
        # Already migrated?
        marker = self.data_dir / ".migrated_to_lineages"
        if marker.is_file():
            return

        meta = self.create(f"migrated_{auto_lineage_name()}")
        dest = self._lineage_dir(meta.id)
        if legacy_graph.is_file():
            (dest / "graph.json").write_bytes(legacy_graph.read_bytes())
        if legacy_files.is_dir():
            dfiles = dest / "files"
            dfiles.mkdir(exist_ok=True)
            for f in legacy_files.iterdir():
                if f.is_file():
                    target = dfiles / f.name
                    if not target.exists():
                        target.write_bytes(f.read_bytes())
        marker.write_text(meta.id + "\n", encoding="utf-8")
