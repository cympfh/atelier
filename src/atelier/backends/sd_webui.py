"""Stable Diffusion WebUI (A1111-compatible) backend."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx

from atelier.backends.base import Backend
from atelier.backends.types import (
    BackendCapabilities,
    GeneratedAsset,
    GenerateMode,
    GenerationError,
    MediaInput,
)
from atelier.config import Settings

log = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_HINT = "WAI-NSFW-illustrious-SDXL"

# name:weight or name (weight defaults to 1.0), comma-separated
_LORA_ENTRY = re.compile(
    r"^\s*([^:<,]+?)(?::\s*([+-]?\d+(?:\.\d+)?))?\s*$",
)

SD_PARAM_SCHEMA: dict[str, Any] = {
    "negative_prompt": {"type": "string", "default": "", "modes": ["t2i", "i2i"]},
    "steps": {"type": "integer", "minimum": 1, "maximum": 150, "default": 28, "modes": ["t2i", "i2i"]},
    "cfg_scale": {"type": "number", "minimum": 1, "maximum": 30, "default": 7.0, "modes": ["t2i", "i2i"]},
    "width": {"type": "integer", "default": 1024, "modes": ["t2i", "i2i"]},
    "height": {"type": "integer", "default": 1024, "modes": ["t2i", "i2i"]},
    "sampler_name": {"type": "string", "default": "Euler a", "modes": ["t2i", "i2i"]},
    "seed": {"type": "integer", "default": -1, "modes": ["t2i", "i2i"]},
    "denoising_strength": {
        "type": "number",
        "minimum": 0,
        "maximum": 1,
        "default": 0.55,
        "modes": ["i2i"],
    },
    "checkpoint": {
        "type": "string",
        "default": "",
        "description": f"sd_model_checkpoint title; prefer {DEFAULT_CHECKPOINT_HINT} if installed",
        "modes": ["t2i", "i2i"],
    },
    # LoRA: "my_lora:0.8, other_lora:0.5" → <lora:my_lora:0.8> appended to prompt
    "lora": {
        "type": "string",
        "default": "",
        "description": "Comma-separated LoRAs as name:weight (A1111 <lora:name:w>)",
        "modes": ["t2i", "i2i"],
    },
    "clip_skip": {
        "type": "integer",
        "minimum": 1,
        "maximum": 12,
        "default": 2,
        "modes": ["t2i", "i2i"],
    },
    "restore_faces": {"type": "boolean", "default": False, "modes": ["t2i", "i2i"]},
    "enable_hr": {"type": "boolean", "default": False, "modes": ["t2i"]},
    "hr_scale": {"type": "number", "minimum": 1, "maximum": 4, "default": 1.5, "modes": ["t2i"]},
    "hr_upscaler": {"type": "string", "default": "Latent", "modes": ["t2i"]},
    "hr_second_pass_steps": {
        "type": "integer",
        "minimum": 0,
        "maximum": 150,
        "default": 0,
        "modes": ["t2i"],
    },
    # Advanced: JSON object string for alwayson_scripts (ControlNet, etc.)
    "alwayson_scripts": {
        "type": "string",
        "default": "",
        "description": 'JSON object for A1111 alwayson_scripts, e.g. {"ControlNet": {...}}',
        "modes": ["t2i", "i2i"],
    },
}


def apply_loras_to_prompt(prompt: str, lora_spec: str | list[Any] | None) -> str:
    """Append <lora:name:weight> tags from a user-friendly spec."""
    tags = parse_lora_tags(lora_spec)
    if not tags:
        return prompt
    # Avoid duplicating tags already present
    extra = [t for t in tags if t not in prompt]
    if not extra:
        return prompt
    base = prompt.rstrip()
    return f"{base} {' '.join(extra)}".strip()


def parse_lora_tags(lora_spec: str | list[Any] | None) -> list[str]:
    if not lora_spec:
        return []
    if isinstance(lora_spec, list):
        tags: list[str] = []
        for item in lora_spec:
            if isinstance(item, str):
                tags.extend(parse_lora_tags(item))
            elif isinstance(item, dict):
                name = item.get("name") or item.get("lora")
                weight = item.get("weight", 1.0)
                if name:
                    tags.append(f"<lora:{name}:{weight}>")
        return tags

    text = str(lora_spec).strip()
    if not text:
        return []
    # Already full tags
    if "<lora:" in text:
        return re.findall(r"<lora:[^>]+>", text) or [text]

    tags = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        m = _LORA_ENTRY.match(part)
        if not m:
            continue
        name = m.group(1).strip()
        weight = m.group(2) if m.group(2) is not None else "1.0"
        tags.append(f"<lora:{name}:{weight}>")
    return tags


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off", ""):
        return False
    return default


def _parse_json_param(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError as e:
            raise GenerationError(f"invalid alwayson_scripts JSON: {e}") from e
        if not isinstance(data, dict):
            raise GenerationError("alwayson_scripts must be a JSON object")
        return data
    raise GenerationError("alwayson_scripts must be object or JSON string")


class SDWebUIBackend(Backend):
    name = "sd_webui"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        probe_on_availability: bool = True,
    ) -> None:
        self._settings = settings
        self._client = client
        self._owns_client = client is None
        self._probe = probe_on_availability
        self._available_cache: tuple[bool, str | None] | None = None

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_t2i=True,
            supports_i2i=True,
            supports_t2v=False,
            supports_i2v=False,
        )

    def param_schema(self) -> dict[str, Any]:
        return SD_PARAM_SCHEMA

    def availability(self) -> tuple[bool, str | None]:
        if not self._settings.sd_webui_url:
            return False, "SD_WEBUI_URL is not set"
        if not self._probe:
            return True, None
        try:
            # WSL↔Windows bridge can add latency; keep probe generous
            with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as c:
                r = c.get(f"{self._settings.sd_webui_url.rstrip('/')}/sdapi/v1/sd-models")
                if r.status_code >= 400:
                    return False, f"SD WebUI HTTP {r.status_code}: {r.text[:200]}"
            return True, None
        except Exception as e:
            return False, f"SD WebUI unreachable: {e}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._settings.http_timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def base(self) -> str:
        return self._settings.sd_webui_url.rstrip("/")

    async def list_models(self) -> list[dict[str, Any]]:
        client = await self._get_client()
        try:
            r = await client.get(f"{self.base}/sdapi/v1/sd-models")
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except httpx.HTTPError as e:
            raise GenerationError(f"SD WebUI list models failed: {e}") from e

    async def set_checkpoint(self, title: str) -> None:
        client = await self._get_client()
        try:
            r = await client.post(
                f"{self.base}/sdapi/v1/options",
                json={"sd_model_checkpoint": title},
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise GenerationError(f"SD WebUI set checkpoint failed: {e}") from e

    async def generate(
        self,
        mode: GenerateMode,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        if mode == GenerateMode.t2i:
            return await self._txt2img(prompt, params)
        if mode == GenerateMode.i2i:
            return await self._img2img(prompt, inputs, params)
        raise GenerationError(f"SD WebUI does not support mode {mode.value}")

    def _common_payload(self, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
        final_prompt = apply_loras_to_prompt(prompt, params.get("lora"))
        payload: dict[str, Any] = {
            "prompt": final_prompt,
            "negative_prompt": params.get("negative_prompt", ""),
            "steps": int(params.get("steps", 28)),
            "cfg_scale": float(params.get("cfg_scale", 7.0)),
            "width": int(params.get("width", 1024)),
            "height": int(params.get("height", 1024)),
            "sampler_name": params.get("sampler_name", "Euler a"),
            "seed": int(params.get("seed", -1)),
            "batch_size": 1,
            "n_iter": 1,
            "restore_faces": _as_bool(params.get("restore_faces"), False),
        }

        override: dict[str, Any] = {}
        ckpt = params.get("checkpoint") or params.get("sd_model_checkpoint")
        if ckpt:
            override["sd_model_checkpoint"] = ckpt
        if params.get("clip_skip") is not None and params.get("clip_skip") != "":
            override["CLIP_stop_at_last_layers"] = int(params["clip_skip"])
        if override:
            payload["override_settings"] = override
            payload["override_settings_restore_afterwards"] = True

        if _as_bool(params.get("enable_hr"), False):
            payload["enable_hr"] = True
            payload["hr_scale"] = float(params.get("hr_scale", 1.5))
            payload["hr_upscaler"] = params.get("hr_upscaler", "Latent")
            hr_steps = int(params.get("hr_second_pass_steps", 0) or 0)
            if hr_steps:
                payload["hr_second_pass_steps"] = hr_steps
            if params.get("denoising_strength") is not None:
                payload["denoising_strength"] = float(params["denoising_strength"])

        scripts = _parse_json_param(params.get("alwayson_scripts"))
        if scripts:
            payload["alwayson_scripts"] = scripts

        return payload

    async def _post_images(self, path: str, payload: dict[str, Any]) -> list[GeneratedAsset]:
        client = await self._get_client()
        try:
            r = await client.post(
                f"{self.base}{path}",
                json=payload,
                timeout=max(self._settings.http_timeout, 300.0),
            )
        except httpx.HTTPError as e:
            raise GenerationError(f"SD WebUI request failed: {e}") from e
        if r.status_code >= 400:
            raise GenerationError(f"SD WebUI HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        images = data.get("images") or []
        if not images:
            raise GenerationError("SD WebUI returned no images")
        out: list[GeneratedAsset] = []
        for b64 in images:
            if isinstance(b64, str) and "," in b64 and b64.startswith("data:"):
                b64 = b64.split(",", 1)[1]
            raw = base64.b64decode(b64)
            out.append(
                GeneratedAsset(
                    data=raw,
                    mime="image/png",
                    params={
                        "steps": payload.get("steps"),
                        "cfg_scale": payload.get("cfg_scale"),
                        "width": payload.get("width"),
                        "height": payload.get("height"),
                        "sampler_name": payload.get("sampler_name"),
                        "seed": payload.get("seed"),
                        "prompt": payload.get("prompt"),
                        "enable_hr": payload.get("enable_hr"),
                        "loras": parse_lora_tags(
                            # re-extract from final prompt tags only for metadata
                            " ".join(re.findall(r"<lora:[^>]+>", payload.get("prompt") or ""))
                        ),
                    },
                )
            )
        return out

    async def _txt2img(self, prompt: str, params: dict[str, Any]) -> list[GeneratedAsset]:
        payload = self._common_payload(prompt, params)
        return await self._post_images("/sdapi/v1/txt2img", payload)

    async def _img2img(
        self,
        prompt: str,
        inputs: list[MediaInput],
        params: dict[str, Any],
    ) -> list[GeneratedAsset]:
        if not inputs:
            raise GenerationError("i2i requires an image input")
        img = inputs[0]
        b64 = base64.b64encode(img.data).decode("ascii")
        payload = self._common_payload(prompt, params)
        payload["init_images"] = [b64]
        payload["denoising_strength"] = float(params.get("denoising_strength", 0.55))
        return await self._post_images("/sdapi/v1/img2img", payload)
