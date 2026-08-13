"""xAI Grok Imagine HTTP client (images + videos)."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from atelier.backends.types import GenerationError

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.x.ai/v1"
DEFAULT_IMAGE_MODEL = "grok-imagine-image-quality"
# T2V / image→video (generations)
DEFAULT_VIDEO_MODEL = "grok-imagine-video-1.5"
# Video edit / extension — docs use grok-imagine-video; 1.5 rejects edits (400)
DEFAULT_VIDEO_EDIT_MODEL = "grok-imagine-video"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def to_data_uri(data: bytes, mime: str) -> str:
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


class GrokClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE,
        http_timeout: float = 60.0,
        video_timeout: float = 600.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http_timeout = http_timeout
        self.video_timeout = video_timeout
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.http_timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        try:
            resp = await client.request(
                method,
                url,
                headers=_auth_headers(self.api_key),
                json=json,
                timeout=timeout or self.http_timeout,
            )
        except httpx.HTTPError as e:
            raise GenerationError(f"xAI request failed: {e}") from e

        if resp.status_code >= 400:
            detail = resp.text[:500]
            raise GenerationError(f"xAI HTTP {resp.status_code}: {detail}")

        try:
            data = resp.json()
        except Exception as e:
            raise GenerationError(f"xAI invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise GenerationError("xAI response is not an object")
        return data

    async def download(self, url: str, *, timeout: float | None = None) -> tuple[bytes, str]:
        client = await self._get_client()
        try:
            resp = await client.get(url, timeout=timeout or self.http_timeout, follow_redirects=True)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise GenerationError(f"failed to download asset: {e}") from e
        ctype = resp.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return resp.content, ctype

    async def upload_file(
        self,
        data: bytes,
        filename: str,
        *,
        mime: str = "application/octet-stream",
        purpose: str = "assistants",
        expires_after: int | None = 86400,
    ) -> str:
        """Upload bytes to xAI Files API; return file_id.

        Video edit docs require a proper .mp4 filename/codec for URL inputs;
        file_id upload with filename ending in .mp4 is the reliable path for v2v.
        """
        client = await self._get_client()
        name = filename if filename.lower().endswith(".mp4") or not mime.startswith("video/") else f"{filename}.mp4"
        # Multipart: expires_after / purpose MUST appear before file (xAI requirement).
        # httpx sends `data` fields before `files`.
        form: dict[str, str] = {"purpose": purpose}
        if expires_after is not None:
            form["expires_after"] = str(expires_after)
        try:
            resp = await client.post(
                f"{self.base_url}/files",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data=form,
                files={"file": (name, data, mime)},
                timeout=max(self.http_timeout, self.video_timeout),
            )
        except httpx.HTTPError as e:
            raise GenerationError(f"xAI file upload failed: {e}") from e
        if resp.status_code >= 400:
            raise GenerationError(f"xAI file upload HTTP {resp.status_code}: {resp.text[:500]}")
        payload = resp.json()
        file_id = payload.get("id")
        if not file_id:
            raise GenerationError(f"xAI file upload missing id: {payload}")
        return str(file_id)

    async def delete_file(self, file_id: str) -> None:
        client = await self._get_client()
        try:
            await client.delete(
                f"{self.base_url}/files/{file_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.http_timeout,
            )
        except httpx.HTTPError:
            log.warning("failed to delete xAI file %s", file_id)

    async def generate_images(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        n: int = 1,
        aspect_ratio: str | None = None,
        response_format: str = "url",
    ) -> list[tuple[bytes, str]]:
        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "response_format": response_format,
        }
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio

        data = await self._request("POST", "/images/generations", json=body)
        return await self._collect_image_payloads(data)

    async def edit_images(
        self,
        prompt: str,
        image_uris: list[str],
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        n: int = 1,
        response_format: str = "url",
    ) -> list[tuple[bytes, str]]:
        if not image_uris:
            raise GenerationError("edit_images requires at least one image")

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "response_format": response_format,
        }
        # Official /v1/images/edits schema (docs.x.ai REST reference):
        # - single:  "image":  { "url": "...", "type": "image_url" }
        # - multi:   "images": [ { "url": "...", "type": "image_url" }, ... ]
        #   mutually exclusive with "image"; up to 3; order = <IMAGE_0>, <IMAGE_1>, ...
        #   (do NOT put multi under "image" as a string list — only first is used / invalid)
        uris = list(image_uris[:3])
        if len(uris) == 1:
            body["image"] = {"url": uris[0], "type": "image_url"}
        else:
            body["images"] = [{"url": u, "type": "image_url"} for u in uris]

        data = await self._request("POST", "/images/edits", json=body)
        return await self._collect_image_payloads(data)

    async def _collect_image_payloads(self, data: dict[str, Any]) -> list[tuple[bytes, str]]:
        items = data.get("data") or data.get("images") or []
        if not items and "url" in data:
            items = [data]
        if not items:
            raise GenerationError(f"no images in xAI response: {list(data.keys())}")

        out: list[tuple[bytes, str]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if b64 := item.get("b64_json") or item.get("base64"):
                raw = base64.b64decode(b64)
                out.append((raw, "image/png"))
                continue
            url = item.get("url")
            if url:
                raw, mime = await self.download(url)
                if not mime.startswith("image/"):
                    mime = "image/png"
                out.append((raw, mime))
        if not out:
            raise GenerationError("could not extract image bytes from xAI response")
        return out

    async def generate_video(
        self,
        prompt: str,
        *,
        model: str = DEFAULT_VIDEO_MODEL,
        image_uri: str | None = None,
        video_uri: str | None = None,
        video_file_id: str | None = None,
        duration: int | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        poll_interval: float = 3.0,
    ) -> tuple[bytes, str]:
        """Text/image-to-video, or video edit when video_file_id / video_uri is set.

        Video edit: use POST /videos/edits. Prefer video_file_id (Files API + .mp4 name);
        bare data: URIs often fail the API's ".mp4 extension" rule and yield no real edit.
        """
        body: dict[str, Any] = {"model": model, "prompt": prompt}
        # Official endpoints (docs.x.ai):
        # - text/image → video: POST /v1/videos/generations  (+ optional image)
        # - video edit:         POST /v1/videos/edits        (+ required video)
        if video_file_id or video_uri:
            if video_file_id:
                body["video"] = {"file_id": video_file_id}
            else:
                body["video"] = {"url": video_uri}
            path = "/videos/edits"
        elif image_uri:
            body["image"] = {"url": image_uri}
            if duration is not None:
                body["duration"] = duration
            if aspect_ratio:
                body["aspect_ratio"] = aspect_ratio
            if resolution:
                body["resolution"] = resolution
            path = "/videos/generations"
        else:
            if duration is not None:
                body["duration"] = duration
            if aspect_ratio:
                body["aspect_ratio"] = aspect_ratio
            if resolution:
                body["resolution"] = resolution
            path = "/videos/generations"

        data = await self._request(
            "POST",
            path,
            json=body,
            timeout=self.http_timeout,
        )

        # Sync response with URL
        video = data.get("video") or {}
        if isinstance(video, dict) and video.get("url"):
            return await self._download_video(video["url"])

        if data.get("url") and data.get("status") in (None, "done", "completed"):
            return await self._download_video(data["url"])

        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            raise GenerationError(f"video generation: no request_id or url: {list(data.keys())}")

        return await self._poll_video(str(request_id), poll_interval=poll_interval)

    async def _poll_video(self, request_id: str, *, poll_interval: float) -> tuple[bytes, str]:
        deadline = asyncio.get_event_loop().time() + self.video_timeout
        while True:
            if asyncio.get_event_loop().time() > deadline:
                raise GenerationError(f"video generation timed out ({self.video_timeout}s)")

            data = await self._request("GET", f"/videos/{request_id}", timeout=self.http_timeout)
            status = (data.get("status") or "").lower()
            if status in ("done", "completed", "succeeded", "success"):
                video = data.get("video") or {}
                if isinstance(video, dict) and video.get("respect_moderation") is False:
                    raise GenerationError("video rejected by moderation (empty url)")
                url = (video.get("url") if isinstance(video, dict) else None) or data.get("url")
                if not url:
                    raise GenerationError(f"video done but no url: {data}")
                return await self._download_video(url)
            if status in ("failed", "expired", "error", "cancelled"):
                err = data.get("error") or data
                raise GenerationError(f"video generation {status}: {err}")

            await asyncio.sleep(poll_interval)

    async def _download_video(self, url: str) -> tuple[bytes, str]:
        raw, mime = await self.download(url, timeout=self.video_timeout)
        if not mime.startswith("video/"):
            mime = "video/mp4"
        return raw, mime
