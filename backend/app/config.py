"""Backend configuration read from environment variables (or `.env` in the service or repo root)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "dev"
    cors_origins: str = "http://localhost:5173"
    ai_service_url: str = "http://localhost:8001"
    internal_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
