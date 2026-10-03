"""Bounded, synchronous PostgreSQL pool; FastAPI runs DB handlers in worker threads."""

from contextlib import contextmanager

from fastapi import Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings
from .errors import AppError


def create_pool() -> ConnectionPool | None:
    """Create a lazy pool for Supabase; tolerate missing configuration at startup."""
    if not settings.supabase_db_url.get_secret_value():
        return None
    return ConnectionPool(
        settings.supabase_db_url.get_secret_value(), min_size=0, max_size=5,
        timeout=5, open=False,
        kwargs={"row_factory": dict_row, "sslmode": "require", "connect_timeout": 5,
                "prepare_threshold": None, "options": "-c statement_timeout=5000 -c search_path=public,extensions"},
    )


@contextmanager
def connection(request: Request):
    """Yield one transaction, committing on success and rolling back on failure."""
    pool = request.app.state.db_pool
    if pool is None:
        raise AppError(500, "INTERNAL_ERROR", "Brak konfiguracji bazy danych")
    with pool.connection() as conn:
        yield conn


def get_repository(request: Request):
    """Provide one request-scoped repository and transaction."""
    from .repository import Repository

    with connection(request) as conn:
        yield Repository(conn)
