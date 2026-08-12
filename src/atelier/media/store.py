"""Local filesystem storage for media bytes."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from atelier.graph.models import MediaKind, MediaNode, new_id

# Extension -> kind
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".gif"}  # gif may be either; prefer image if ambiguous

_MIME_TO_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
}


def kind_from_mime(mime: str) -> MediaKind:
    if mime.startswith("video/"):
        return MediaKind.video
    if mime.startswith("image/"):
        return MediaKind.image
    raise ValueError(f"unsupported mime type: {mime}")


def kind_from_filename(name: str) -> MediaKind | None:
    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXTS and ext != ".gif":
        return MediaKind.image
    if ext in _VIDEO_EXTS and ext != ".gif":
        return MediaKind.video
    if ext == ".gif":
        return MediaKind.image
    return None


def ext_for_mime(mime: str, fallback_name: str | None = None) -> str:
    if mime in _MIME_TO_EXT:
        return _MIME_TO_EXT[mime]
    guessed = mimetypes.guess_extension(mime.split(";")[0].strip())
    if guessed:
        return guessed
    if fallback_name:
        suffix = Path(fallback_name).suffix
        if suffix:
            return suffix.lower()
    return ".bin"


def mime_from_filename(name: str) -> str:
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"


class MediaStore:
    """Save and resolve media files under data_dir/files/."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.files_dir = data_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        path = (self.files_dir / filename).resolve()
        if not str(path).startswith(str(self.files_dir.resolve())):
            raise ValueError("invalid filename")
        return path

    def path_for_node(self, node: MediaNode) -> Path:
        return self.path_for(node.filename)

    def save_bytes(
        self,
        data: bytes,
        *,
        mime: str,
        backend: str | None = None,
        prompt: str | None = None,
        params: dict | None = None,
        parent_ids: list[str] | None = None,
        original_name: str | None = None,
        node_id: str | None = None,
    ) -> MediaNode:
        kind = kind_from_mime(mime)
        nid = node_id or new_id()
        ext = ext_for_mime(mime, original_name)
        filename = f"{nid}{ext}"
        path = self.path_for(filename)
        path.write_bytes(data)

        return MediaNode(
            id=nid,
            kind=kind,
            filename=filename,
            mime=mime,
            backend=backend,
            prompt=prompt,
            params=params or {},
            parent_ids=list(parent_ids or []),
            original_name=original_name,
        )

    def read_bytes(self, node: MediaNode) -> bytes:
        path = self.path_for_node(node)
        if not path.is_file():
            raise FileNotFoundError(node.id)
        return path.read_bytes()

    def delete_file(self, node: MediaNode) -> None:
        path = self.path_for_node(node)
        if path.is_file():
            path.unlink()
