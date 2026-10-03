"""Backend API entry point. Modules (segments, ratings, ...) are added on their own branches."""

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings

VERSION = "0.1.0"

app = FastAPI(title="Rate Your Ride API", version=VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")


async def _check_ai() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(f"{settings.ai_service_url}/health")
        return "ok" if res.status_code == 200 else "error"
    except httpx.HTTPError:
        return "error"


@api.get("/health")
async def health():
    """Service health in the contract format (docs/CONTRACT.md, section 5.1)."""
    checks = {
        "database": "not_configured",  # real check added with db/schema + backend/core
        "ai_service": await _check_ai(),
        "routing": "not_configured",
    }
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return JSONResponse({"status": status, "version": VERSION, "checks": checks})


app.include_router(api)
