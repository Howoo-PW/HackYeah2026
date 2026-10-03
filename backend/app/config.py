"""Backend configuration read from environment variables (or `.env` in the service or repo root)."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ROOT / "backend/.env"), extra="ignore")

    app_env: str = "dev"
    cors_origins: str = "http://localhost:5173"
    ai_service_url: str = "http://localhost:8001"
    internal_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: SecretStr = SecretStr("")
    supabase_service_role_key: SecretStr = SecretStr("")
    supabase_db_url: SecretStr = SecretStr("")
    redis_url: SecretStr = SecretStr("redis://localhost:16379/0")
    routing_provider: str = "ors"
    ors_api_key: SecretStr = SecretStr("")

    ors_base_url: str = "https://api.openrouteservice.org"
    user_agent: str = "RateYourRide/0.1 (hackathon project)"

    @property
    def cors_origin_list(self) -> list[str]:
        """Return the explicitly configured frontend origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
