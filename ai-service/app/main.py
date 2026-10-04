"""AI service entry point (docs/CONTRACT.md, section 6). Internal only: called by the backend."""

import logging
import secrets

from fastapi import Depends, FastAPI, Header

from .assistant_mock import mock_answer, mock_plan
from .assistant_schemas import AnswerOut, AnswerRequest, AssistantRequest, EmbedOut, EmbedRequest, PlanOut
from .config import settings
from .errors import AppError, install_error_handlers
from .mock import MOCK_MODEL, MOCK_SUMMARY, MOCK_SURFACE, mock_embedding
from .schemas import SummarizeRequest, SummaryOut, SurfaceOut, SurfaceRequest

log = logging.getLogger("ai")

app = FastAPI(title="Rate My Road AI", version="0.1.0")
install_error_handlers(app)


def require_internal_key(x_internal_key: str | None = Header(default=None)) -> None:
    """Every endpoint except /health needs X-Internal-Key equal to INTERNAL_API_KEY."""
    expected = settings.internal_api_key
    if not expected or not x_internal_key or not secrets.compare_digest(x_internal_key, expected):
        raise AppError(401, "UNAUTHORIZED", "Missing or invalid X-Internal-Key")


async def _call_llm(fn, req):
    # Imported lazily so mock mode works without LangChain or provider credentials.
    from . import llm

    try:
        return await getattr(llm, fn)(req)
    except Exception as exc:  # any provider, timeout, config or parsing failure
        log.exception("LLM call %s failed", fn)
        raise AppError(502, "UPSTREAM_ERROR", "AI provider call failed", {"reason": type(exc).__name__}) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "provider": settings.ai_provider,
        "model": settings.ai_model or None,
        "mock": settings.mock_ai,
    }


@app.post("/summarize", response_model=SummaryOut, dependencies=[Depends(require_internal_key)])
async def summarize(req: SummarizeRequest) -> SummaryOut:
    if settings.mock_ai:
        content, model = MOCK_SUMMARY, MOCK_MODEL
    else:
        content, model = await _call_llm("summarize", req), settings.ai_model
    return SummaryOut(**content.model_dump(), comments_count=len(req.comments), model=model)


@app.post("/analyze-surface", response_model=SurfaceOut, dependencies=[Depends(require_internal_key)])
async def analyze_surface(req: SurfaceRequest) -> SurfaceOut:
    if settings.mock_ai:
        return MOCK_SURFACE
    return await _call_llm("analyze_surface", req)


@app.post("/assistant/plan", response_model=PlanOut, dependencies=[Depends(require_internal_key)])
async def assistant_plan(req: AssistantRequest) -> PlanOut:
    """A request in words ("rowerem z Rynku na Wawel, ładne widoki") as a plan the backend can execute."""
    if settings.mock_ai:
        plan, model = mock_plan(req.query), MOCK_MODEL
    else:
        plan, model = await _call_llm("plan", req), settings.ai_model
    return PlanOut(**plan.model_dump(), model=model)


@app.post("/assistant/answer", response_model=AnswerOut, dependencies=[Depends(require_internal_key)])
async def assistant_answer(req: AnswerRequest) -> AnswerOut:
    """The reply to the user, written only from the facts the backend collected (ratings, comments, obstacles)."""
    if settings.mock_ai:
        return AnswerOut(answer=mock_answer(req), model=MOCK_MODEL)
    content = await _call_llm("answer", req)
    return AnswerOut(**content.model_dump(), model=settings.ai_model)


@app.post("/embed", response_model=EmbedOut, dependencies=[Depends(require_internal_key)])
async def embed(req: EmbedRequest) -> EmbedOut:
    """Vectors for comments and search descriptions (1536 numbers each), for finding comments by meaning."""
    if settings.mock_ai:
        return EmbedOut(vectors=[mock_embedding(t) for t in req.texts], model=MOCK_MODEL)
    return EmbedOut(vectors=await _call_llm("embed", req.texts), model=settings.ai_embedding_model)
