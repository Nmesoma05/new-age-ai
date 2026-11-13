"""Logs, error tracking and readiness for deployed environments.

Logs: one JSON object per line on stdout (LOG_FORMAT=json), carrying the request id, env and release. A request
line holds method, path, status and duration only: never query strings, bodies, headers, tokens or emails.
Error tracking: Sentry when SENTRY_DSN is set; personal data is not sent (no PII, no request bodies or cookies).
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time

from app.core.config import get_settings

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_STD = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {"message", "asctime"}
_REDACT = {"password", "token", "secret", "authorization", "cookie", "email", "body", "api_key"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        s = get_settings()
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
               "level": record.levelname.lower(), "logger": record.name, "msg": record.getMessage(),
               "env": s.env, "release": s.release,
               "request_id": getattr(record, "request_id", None) or request_id_var.get()}
        for k, v in vars(record).items():
            if k not in _STD and not k.startswith("_"):
                out[k] = "[redacted]" if k.lower() in _REDACT else v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging() -> None:
    s = get_settings()
    root = logging.getLogger()
    if getattr(root, "_eco_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if s.log_format == "json" else
                         logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our request line (no query strings)
    root._eco_configured = True  # type: ignore[attr-defined]


def _scrub(event, _hint):
    req = event.get("request") or {}
    for k in ("data", "cookies", "headers", "query_string", "env"):
        req.pop(k, None)
    event.pop("user", None)
    return event


def setup_error_tracking() -> bool:
    s = get_settings()
    if not s.sentry_dsn:
        return False
    import sentry_sdk  # optional dependency, installed in the production image
    sentry_sdk.init(dsn=s.sentry_dsn.get_secret_value(), environment=s.env, release=s.release,
                    send_default_pii=False, traces_sample_rate=0.05, max_request_body_size="never",
                    before_send=_scrub)
    return True
