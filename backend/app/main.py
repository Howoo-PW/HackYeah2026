"""Backend API entry point. Modules (segments, ratings, ...) are added on their own branches."""

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .core import router as core_router
from .database import create_pool
from .errors import install_error_handlers
from .rate_limit import RateLimiter
from .routing.router import router as routing_router

VERSION = "0.1.0"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open and close the bounded DB pool with the application."""
    pool = create_pool()
    app.state.db_pool = pool
    if pool is not None:
        pool.open(wait=False)
    try:
        yield
    finally:
        if pool is not None:
            pool.close()


app = FastAPI(title="Rate Your Ride API", version=VERSION, lifespan=lifespan)
app.state.db_pool = None
app.state.rate_limiter = RateLimiter()
install_error_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")
api.include_router(core_router)
api.include_router(routing_router)


async def _check_ai() -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            res = await client.get(f"{settings.ai_service_url}/health")
        return "ok" if res.status_code == 200 else "error"
    except httpx.HTTPError:
        return "error"


def _check_database() -> str:
    """Check credentials, PostGIS and all contracted relations without writes."""
    pool = app.state.db_pool
    if pool is None:
        return "not_configured"
    try:
        with pool.connection() as conn:
            row = conn.execute("""
                SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'postgis')
                    AND NOT EXISTS (
                        SELECT 1 FROM unnest(ARRAY['profiles','segments','ratings','comments',
                            'obstacles','parking_spots','segment_photos','segment_summaries',
                            'segment_stats']) AS name
                        WHERE to_regclass('public.' || name) IS NULL
                    ) AS ready
            """).fetchone()
            return "ok" if row["ready"] else "schema_missing"
    except Exception:
        return "error"


def _check_routing() -> str:
    # Avoid consuming routing provider quotas during each health poll.
    if settings.routing_provider == "ors":
        return "ok" if settings.ors_api_key.get_secret_value() else "not_configured"
    return "ok" if settings.routing_provider == "mock" else "not_configured"


@api.get("/health", tags=["system"])
async def health():
    """Service health in the contract format (docs/CONTRACT.md, section 5.1)."""
    database, ai = await asyncio.gather(asyncio.to_thread(_check_database), _check_ai())
    checks = {"database": database, "ai_service": ai, "routing": _check_routing()}
    status = "down" if database != "ok" else ("ok" if all(v == "ok" for v in checks.values()) else "degraded")
    return JSONResponse({"status": status, "version": VERSION, "checks": checks}, status_code=503 if status == "down" else 200)


app.include_router(api)
