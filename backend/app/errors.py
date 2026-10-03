"""Errors in the shared contract format, without request bodies or secrets."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import Error as DatabaseError
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException


class AppError(Exception):
    """An expected API error that is safe to return to the client."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def _body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    """Install safe handlers for application, validation, HTTP and database errors."""

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", ())[1:]) or None
        return JSONResponse(_body("VALIDATION_ERROR", "Nieprawidłowe dane żądania", {"field": field}), status_code=422)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        codes = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "BAD_REQUEST"}
        return JSONResponse(_body(codes.get(exc.status_code, "INTERNAL_ERROR"), str(exc.detail)), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(PoolTimeout)
    @app.exception_handler(DatabaseError)
    async def database_error(_: Request, exc: Exception):
        # Database errors can contain connection credentials or user content.
        logging.getLogger(__name__).error("Database request failed: %s", type(exc).__name__)
        return JSONResponse(_body("INTERNAL_ERROR", "Baza danych jest niedostępna"), status_code=500)

    @app.exception_handler(Exception)
    async def internal_error(_: Request, exc: Exception):
        logging.getLogger(__name__).error("Request failed: %s", type(exc).__name__)
        return JSONResponse(_body("INTERNAL_ERROR", "Błąd serwera"), status_code=500)
