"""Runtime configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4.6"
    openrouter_http_referer: str = "http://localhost:5173"
    openrouter_x_title: str = "hiring-sim-v0"

    # --- Auth ---
    manager_username: str = "manager"
    manager_password: str = "changeme"

    # --- DB ---
    database_url: str = "sqlite:///./hiring_sim.db"

    # --- CORS ---
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]


settings = Settings()
