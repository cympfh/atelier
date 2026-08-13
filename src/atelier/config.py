"""Application configuration from environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # xAI Grok
    xai_api_key: str | None = Field(default=None, alias="XAI_API_KEY")

    # Stable Diffusion WebUI (A1111-compatible)
    # Forge on this machine uses 7862 (not classic 7860)
    sd_webui_url: str = Field(default="http://127.0.0.1:7862", alias="SD_WEBUI_URL")

    # Tag groups for prompt suggest (tagskeeper-compatible TOML)
    tags_toml: Path | None = Field(
        default=None,
        alias="ATELIER_TAGS_TOML",
        description="Path to tags.toml (default: ~/git/tagskeeper/tags.toml if present)",
    )

    # HTTP server
    host: str = Field(default="0.0.0.0", alias="ATELIER_HOST")
    port: int = Field(default=8000, alias="ATELIER_PORT")

    # Storage
    data_dir: Path = Field(default=Path("data"), alias="ATELIER_DATA_DIR")

    # Timeouts (seconds)
    http_timeout: float = Field(default=60.0, alias="ATELIER_HTTP_TIMEOUT")
    video_timeout: float = Field(default=600.0, alias="ATELIER_VIDEO_TIMEOUT")

    # Dev: register offline Echo backend
    include_echo_backend: bool = Field(default=False, alias="ATELIER_ECHO")

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def resolve_tags_toml(self) -> Path | None:
        if self.tags_toml is not None:
            p = Path(self.tags_toml).expanduser()
            return p if p.is_file() else None
        default = Path.home() / "git" / "tagskeeper" / "tags.toml"
        return default if default.is_file() else None


def get_settings() -> Settings:
    return Settings()
