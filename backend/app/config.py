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

    # --- DB ---
    database_url: str = "sqlite:///./hiring_sim.db"

    # --- Supabase ---
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    # Derived automatically from supabase_url if left empty.
    supabase_jwks_url: str = ""

    # --- Auth ---
    # Comma-separated list of Google emails that get the manager role.
    manager_emails: str = ""
    # Legacy basic-auth (kept for local fallback; ignored when DEV_MODE=false
    # and Supabase is configured).
    manager_username: str = "manager"
    manager_password: str = "changeme"
    # Skip JWT verification in local dev (never set true in compose/prod).
    dev_mode: bool = False

    # --- CORS ---
    cors_allow_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    @property
    def jwks_url(self) -> str:
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"
        return ""

    @property
    def manager_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.manager_emails.split(",") if e.strip()}

    @property
    def use_alembic(self) -> bool:
        return self.database_url.startswith("postgresql")


settings = Settings()
