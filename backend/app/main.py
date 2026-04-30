"""FastAPI application entrypoint.

Wires together routers, middleware, error handlers, rate limiting, and
request-id propagation. Every request gets a UUID request_id stored on
request.state and echoed in audit_log + error responses.
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth as auth_routes
from app.api import health as health_routes
from app.api import me as me_routes
from app.config import get_settings
from app.core.errors import install_error_handlers
from app.core.rate_limit import limiter

logging.basicConfig(level=get_settings().LOG_LEVEL.upper())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request_id (UUID) to every request and echo it as a header."""

    async def dispatch(self, request: Request, call_next):
        rid = uuid.uuid4()
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(rid)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly validate settings — fail fast if env is misconfigured.
    get_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="aurum-platform",
        version="0.1.0",
        docs_url=None if settings.APP_ENV == "production" else "/docs",
        redoc_url=None,
        openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
        lifespan=lifespan,
    )

    # Rate limiting (slowapi attaches via state)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS — credentials required for the refresh cookie
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    app.add_middleware(RequestContextMiddleware)

    install_error_handlers(app)

    app.include_router(health_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(me_routes.router)

    return app


app = create_app()
