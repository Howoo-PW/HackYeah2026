"""Backend configuration read from environment variables (or `.env` in the service or repo root)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "dev"
    cors_origins: str = "http://localhost:5173"
    ai_service_url: str = "http://localhost:8001"
    internal_api_key: str = ""

    # routing: "ors" needs ORS_API_KEY, anything else (or no key) falls back to the mock provider
    routing_provider: str = "mock"
    ors_api_key: str = ""
    ors_base_url: str = "https://api.openrouteservice.org"
    user_agent: str = "RateYourRide/0.1 (hackathon project)"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
