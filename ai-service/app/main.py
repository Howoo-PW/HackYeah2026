"""AI service entry point. /summarize and /analyze-surface are added on branch ai/service."""

from fastapi import FastAPI

from .config import settings

app = FastAPI(title="Rate Your Ride AI", version="0.1.0")


@app.get("/health")
def health():
    """Service health in the contract format (docs/CONTRACT.md, section 6)."""
    return {
        "status": "ok",
        "provider": settings.ai_provider,
        "model": settings.ai_model or None,
        "mock": settings.mock_ai,
    }
