"""Backend API entry point. Modules (segments, ratings, ...) are added on their own branches."""

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .errors import install_error_handlers
from .routing.router import router as routing_router

VERSION = "0.1.0"

app = FastAPI(title="Rate Your Ride API", version=VERSION)
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")
api.include_router(routing_router)


async def _check_ai() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(f"{settings.ai_service_url}/health")
        return "ok" if res.status_code == 200 else "error"
    except httpx.HTTPError:
        return "error"


def _check_routing() -> str:
    # No call to ORS here: the free plan has a daily quota and /health is polled.
    if settings.routing_provider == "ors":
        return "ok" if settings.ors_api_key else "not_configured"
    return "ok"  # mock provider


@api.get("/health")
async def health():
    """Service health in the contract format (docs/CONTRACT.md, section 5.1)."""
    checks = {
        "database": "not_configured",  # real check added with db/schema + backend/core
        "ai_service": await _check_ai(),
        "routing": _check_routing(),
    }
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return JSONResponse({"status": status, "version": VERSION, "checks": checks})


app.include_router(api)
