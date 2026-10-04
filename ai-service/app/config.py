"""AI service configuration read from environment variables (or `.env` in the service or repo root)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    internal_api_key: str = ""
    mock_ai: bool = True
    ai_provider: str = "google_genai"
    ai_model: str = ""
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    # "json_mode": for models that ignore tool/JSON schemas; the schema is then spelled out in the prompt.
    ai_structured_method: str | None = None
    # Reasoning models: "minimal" (native OpenAI gpt-5 family) or "low" (OpenRouter) cuts latency a lot.
    ai_reasoning_effort: str | None = None
    # Embeddings (comment search by meaning); OpenAI-compatible API, same key and base URL as the chat model.
    ai_embedding_model: str = "text-embedding-3-small"
    ai_timeout_s: float = 12.0  # below the backend's 15 s timeout from the contract


settings = Settings()
