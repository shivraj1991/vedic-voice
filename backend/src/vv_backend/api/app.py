"""FastAPI application factory.

`create_app()` wires settings, DB, Clerk keys, storage and the scoring client.
Tests and local dev pass fakes; production builds everything from the
environment (`Settings.from_env()`).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from ..content import InvalidEdit, NotFound, PermissionDenied
from ..db.session import make_engine
from . import routes_admin, routes_learner, routes_public
from .auth import ClerkJWKS, KeyProvider, StaticJWKS
from .deps import SlidingWindowLimiter
from .scoring_client import LambdaScorer, Scorer
from .settings import Settings
from .storage import R2Storage, Storage


def create_app(
    settings: Settings | None = None,
    *,
    session_factory=None,
    keys: KeyProvider | None = None,
    storage: Storage | None = None,
    scorer: Scorer | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    dev = settings.env != "prod"
    app = FastAPI(
        title="Vedic Voice API",
        version="0.1.0",
        docs_url="/docs" if dev else None,  # no public API explorer in production
        redoc_url=None,
        openapi_url="/openapi.json" if dev else None,
    )
    app.state.settings = settings
    app.state.session_factory = session_factory or sessionmaker(
        bind=make_engine(), expire_on_commit=False
    )
    if keys is None:
        keys = StaticJWKS.from_file(settings.dev_jwks_path) if settings.dev_jwks_path else (
            ClerkJWKS(settings.clerk_jwks_url))  # fmt: skip
    app.state.keys = keys
    app.state.storage = storage if storage is not None else (
        R2Storage(settings.r2) if settings.r2 else None)  # fmt: skip
    app.state.scorer = scorer if scorer is not None else (
        LambdaScorer(settings.scoring_function, settings.aws_region)
        if settings.scoring_function else None)  # fmt: skip
    app.state.upload_limiter = SlidingWindowLimiter(settings.upload_urls_per_minute, 60)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "PUT", "PATCH"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(PermissionDenied)
    def _forbidden(_: Request, exc: PermissionDenied) -> JSONResponse:
        return JSONResponse({"detail": "insufficient role"}, status_code=403)

    @app.exception_handler(NotFound)
    def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": "not found"}, status_code=404)

    @app.exception_handler(InvalidEdit)
    def _invalid(_: Request, exc: InvalidEdit) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    app.include_router(routes_public.router)
    app.include_router(routes_learner.router)
    app.include_router(routes_admin.router)
    return app
