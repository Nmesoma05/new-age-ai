from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ops
from app.api.v1 import (
    admin,
    assistant,
    auth,
    billing,
    business,
    content,
    creator,
    documents,
    freelancer,
    integrations,
    orgs,
    profiles,
    workspaces,
)
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.errors import install_error_handlers
from app.core.observability import setup_error_tracking, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    setup_logging()
    setup_error_tracking()
    app = FastAPI(title="New Age AI API", version="0.1.0", lifespan=lifespan,
                  docs_url=None if s.is_deployed else "/docs", redoc_url=None,
                  description="Multi-tenant API for the Creator & Marketing, Business Marketing and Freelancer Growth "
                              "products. All errors are application/problem+json with a stable `code`.")
    install_error_handlers(app)
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-Id"])
    for r in (auth, orgs, workspaces, profiles, documents, content, assistant, creator, business, freelancer, integrations, billing, admin):
        app.include_router(r.router)
    for r in (creator.clients, creator.public, business.accounts, freelancer.accounts):
        app.include_router(r)

    app.include_router(ops.router)

    return app


app = create_app()
