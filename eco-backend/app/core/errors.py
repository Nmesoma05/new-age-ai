"""Consistent error responses: RFC 9457 problem+json with a stable machine-readable `code`."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.observability import request_id_var

log = logging.getLogger("app.errors")
access = logging.getLogger("eco.access")
PROBLEM = "application/problem+json"


class AppError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None,
                 headers: dict[str, str] | None = None, extra: dict | None = None):
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.headers, self.extra = headers or {}, extra or {}


def not_found(what: str = "resource") -> AppError:
    # Used for both "does not exist" and "exists but you can't see it", so existence never leaks.
    return AppError(404, f"{what}_not_found", "Not found", f"The {what.replace('_', ' ')} was not found.")


def forbidden(detail: str, code: str = "forbidden") -> AppError:
    return AppError(403, code, "Forbidden", detail)


def _body(request: Request, status: int, code: str, title: str, detail: str | None, extra: dict | None = None) -> dict:
    body = {"type": f"https://docs.ecosystem.example/errors/{code}", "title": title, "status": status,
            "code": code, "request_id": getattr(request.state, "request_id", None)}
    if detail:
        body["detail"] = detail
    if extra:
        body.update(extra)
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_mw(request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = rid[:64]
        token = request_id_var.set(request.state.request_id)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
            if request.url.path not in ("/health", "/ready"):
                access.info("request", extra={"request_id": request.state.request_id,
                                              "method": request.method, "path": request.url.path[:200],
                                              "status": response.status_code,
                                              "ms": round((time.perf_counter() - t0) * 1000)})
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request.state.request_id
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("referrer-policy", "no-referrer")
        # Responses carry personal/tenant data: never store them in browser or shared caches (QA BUG-09)
        response.headers.setdefault("cache-control", "no-store")
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.status, exc.code, exc.title, exc.detail, exc.extra),
                            status_code=exc.status, media_type=PROBLEM, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")}
                  for e in exc.errors()]
        return JSONResponse(_body(request, 422, "validation_failed", "Invalid request",
                                  "One or more fields are invalid.", {"errors": errors}),
                            status_code=422, media_type=PROBLEM)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                413: "payload_too_large"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(request, exc.status_code, code, str(exc.detail), None),
                            status_code=exc.status_code, media_type=PROBLEM, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", None)})
        return JSONResponse(_body(request, 500, "internal_error", "Something went wrong",
                                  "The error was logged. Try again or contact support with the request id."),
                            status_code=500, media_type=PROBLEM)
