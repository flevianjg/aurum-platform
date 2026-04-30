"""Centralized exception handlers.

Returns RFC-7807-ish JSON errors; never leaks stack traces or internal detail
to the client. Every error path with a user-id is also written to audit_log
by the route that raised it.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for application-defined errors."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "internal error") -> None:
        super().__init__(message)
        self.message = message


class AuthError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def _problem(
    *, status_code: int, code: str, message: str, request_id: str | None = None
) -> JSONResponse:
    body: dict[str, str | int] = {
        "error": code,
        "message": message,
        "status": status_code,
    }
    if request_id:
        body["request_id"] = str(request_id)
    return JSONResponse(status_code=status_code, content=body)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _problem(
            status_code=exc.status_code,
            code="http_error",
            message=str(exc.detail),
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning("validation error on %s: %s", request.url.path, exc.errors())
        return _problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="request validation failed",
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limited(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return _problem(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message="too many requests",
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database error")
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="database_error",
            message="database error",
            request_id=getattr(request.state, "request_id", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception")
        return _problem(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_error",
            message="internal server error",
            request_id=getattr(request.state, "request_id", None),
        )
