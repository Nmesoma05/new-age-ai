"""Liveness and readiness for the load balancer, the deploy pipeline and uptime monitoring.

/health = the process is up (no dependencies): restart the container if this fails.
/ready  = this instance can serve traffic: database reachable, schema at the deployed migration head, file storage
          writable and readable, virus scanner answering (when enabled). The pipeline waits for /ready after a deploy
          and the load balancer routes only to ready instances. Failing check names are returned; no details.
"""
from __future__ import annotations

import asyncio
import socket
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import transaction
from app.services.storage import get_storage

router = APIRouter(tags=["ops"])
ROOT = Path(__file__).resolve().parents[2]


@lru_cache
def migration_head() -> str:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg).get_current_head()


async def _db() -> bool:
    async with transaction(None, context="system") as s:
        v = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    return v == migration_head()


async def _storage() -> bool:
    st, key = get_storage(), "_ready/probe"
    await st.put(key, b"ok")
    ok = await st.get(key) == b"ok"
    await st.delete(key)
    return ok


async def _scanner() -> bool:
    s = get_settings()
    if s.file_scanner == "disabled_dev_only":
        return True

    def ping() -> bool:
        with socket.create_connection((s.clamav_host, s.clamav_port), timeout=3) as sock:
            sock.sendall(b"zPING\0")
            return sock.recv(16).startswith(b"PONG")
    return await asyncio.to_thread(ping)


@router.get("/health")
async def health():
    s = get_settings()
    return {"status": "ok", "release": s.release}


@router.get("/ready")
async def ready():
    checks = {"database": _db, "storage": _storage, "scanner": _scanner}
    if not get_settings().uploads_enabled:  # preview: no file storage or scanner to check
        checks = {"database": _db}
    results: dict[str, bool] = {}
    for name, fn in checks.items():
        try:
            results[name] = await asyncio.wait_for(fn(), timeout=5)
        except Exception:  # noqa: BLE001 - any failure means not ready; details go to logs, not the response
            results[name] = False
    ok = all(results.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": results,
                         "release": get_settings().release}, status_code=200 if ok else 503)
