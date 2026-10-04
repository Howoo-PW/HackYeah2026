"""Comment embeddings (pgvector): vectors made by the AI service, stored in public.comment_embeddings, searched by meaning.

A new comment is embedded in the background (best effort: failures are logged, the comment is saved either way); older comments
are filled in by scripts/embed_comments.py. Only visible comments are ever returned by a search.
"""

import logging

import httpx

from .config import settings
from .errors import AppError

log = logging.getLogger("embeddings")

BATCH = 64
TIMEOUT_S = 20


def vector_literal(vector: list[float]) -> str:
    """pgvector text form of a vector ('[0.1,0.2,...]'), passed as a parameter and cast with ::vector."""
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def embed_sync(texts: list[str]) -> tuple[list[list[float]], str]:
    """Vectors and the model name from the AI service (blocking; for background work and scripts)."""
    try:
        response = httpx.post(f"{settings.ai_service_url}/embed", json={"texts": texts}, headers={"X-Internal-Key": settings.internal_api_key}, timeout=TIMEOUT_S)
        response.raise_for_status()
        body = response.json()
        return body["vectors"], body["model"]
    except (httpx.HTTPError, ValueError, KeyError):
        raise AppError(502, "AI_UNAVAILABLE", "Usługa embeddingów jest chwilowo niedostępna") from None


def index_comment(pool, comment_id) -> None:
    """Embed one new comment and store the vector. Never raises: it runs after the response was sent."""
    try:
        with pool.connection() as conn:
            row = conn.execute("SELECT text FROM public.comments WHERE id = %s AND status = 'visible'", (comment_id,)).fetchone()
        if row is None:
            return
        vectors, model = embed_sync([row["text"]])
        with pool.connection() as conn:
            conn.execute("""
                INSERT INTO public.comment_embeddings (comment_id, embedding, model) VALUES (%s, %s::vector, %s)
                ON CONFLICT (comment_id) DO UPDATE SET embedding = excluded.embedding, model = excluded.model
            """, (comment_id, vector_literal(vectors[0]), model))
    except Exception:  # background work must never raise
        log.warning("embedding of comment %s failed", comment_id, exc_info=True)
