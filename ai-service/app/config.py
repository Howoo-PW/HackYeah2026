"""AI service configuration read from environment variables (or `.env` in the service or repo root)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    internal_api_key: str = ""
    mock_ai: bool = True
    ai_provider: str = "google_genai"
    ai_model: str = ""


settings = Settings()
