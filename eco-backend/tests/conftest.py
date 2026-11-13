"""Test harness: a fresh PostgreSQL database per test session, migrated with Alembic, accessed by the API
through the non-owner `eco_app` role so row-level security is live in every test.

Environment (defaults match the local dev setup in README):
  TEST_PG_HOST, TEST_PG_OWNER, TEST_PG_OWNER_PASSWORD, TEST_PG_APP, TEST_PG_APP_PASSWORD
"""
from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass

import psycopg
import pytest
from cryptography.fernet import Fernet

HOST = os.environ.get("TEST_PG_HOST", "localhost")
OWNER = os.environ.get("TEST_PG_OWNER", "eco_owner")
OWNER_PW = os.environ.get("TEST_PG_OWNER_PASSWORD", "owner_dev_pw")
APP = os.environ.get("TEST_PG_APP", "eco_app")
APP_PW = os.environ.get("TEST_PG_APP_PASSWORD", "app_dev_pw")
DB = os.environ.setdefault("ECO_TEST_DB", f"eco_test_{secrets.token_hex(4)}")
OWNER_DSN = f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/{DB}"
APP_DSN = f"postgresql://{APP}:{APP_PW}@{HOST}/{DB}"
STORAGE_DIR = os.environ.setdefault("ECO_TEST_STORAGE", f"/tmp/eco-test-storage-{secrets.token_hex(4)}")

os.environ.update({
    "ENV": "test",
    "DATABASE_URL": f"postgresql+psycopg://{APP}:{APP_PW}@{HOST}/{DB}",
    "MIGRATIONS_DATABASE_URL": f"postgresql+psycopg://{OWNER}:{OWNER_PW}@{HOST}/{DB}",
    "JWT_SECRET": secrets.token_urlsafe(48),
    "CREDENTIALS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "FILE_SCANNER": "disabled_dev_only",
    "STORAGE_LOCAL_DIR": STORAGE_DIR,
    "AI_PRICE_IN_PER_1M_USD": "1.0",
    "AI_PRICE_OUT_PER_1M_USD": "4.0",
    "AI_RATE_LIMIT_PER_MINUTE": "1000",
    "PAYSTACK_SECRET_KEY": "sk_test_" + secrets.token_hex(16),
    "EMBEDDING_PROVIDER": "hash_dev_only",
    "EMAIL_BACKEND": "dev_outbox",  # captured in email_outbox, never sent
    "OUTBOUND_HTTP_ENABLED": "false",  # tests never reach real providers; integration tests inject a transport
})

TABLES_TO_CLEAN = [
    "auth_attempts", "password_reset_tokens", "email_outbox", "integration_calls", "oauth_states", "external_cache",
    "interview_sessions", "applications", "opportunities", "marketing_results",
    "follower_snapshots", "post_metrics", "asset_comments", "review_links", "calendar_items", "campaigns",
    "pending_actions", "tool_calls", "memory_items", "document_chunks", "agent_runs",
    "audit_events", "messages", "asset_versions", "assets", "conversations", "ai_usage_records", "documents",
    "professional_profiles", "business_profiles", "client_accounts", "projects", "workspace_members", "workspaces",
    "integrations", "webhook_events", "usage_counters", "subscriptions", "product_access", "team_members", "teams",
    "org_members", "organisations", "refresh_tokens", "users",
]


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/postgres", autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{DB}"')
    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute(f'GRANT CONNECT ON DATABASE "{DB}" TO {APP}')
        c.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    from alembic import command
    from alembic.config import Config
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")
    yield
    import time
    for attempt in range(5):  # a background worker (e.g. autovacuum) can briefly hold a connection
        try:
            with psycopg.connect(f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/postgres", autocommit=True) as c:
                c.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
            break
        except psycopg.errors.InsufficientPrivilege:
            time.sleep(1 + attempt)


@pytest.fixture
def owner_db():
    """Direct owner connection, for test setup and assertions only (bypasses RLS as table owner)."""
    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        yield c


@pytest.fixture(autouse=True)
async def clean(database):
    yield
    from app.core.db import dispose_engine
    await dispose_engine()
    with psycopg.connect(OWNER_DSN, autocommit=True) as c:
        c.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update")
        c.execute(f"TRUNCATE {', '.join(TABLES_TO_CLEAN)} RESTART IDENTITY CASCADE")
        c.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update")


@pytest.fixture
def provider():
    """Stands in for the external LLM API only. Everything else (DB, files, retrieval, usage) is real."""
    from tests.ai.scripted import ScriptedProvider
    return ScriptedProvider()


@pytest.fixture
def research():
    return None


@pytest.fixture
async def client(provider, research):
    import httpx

    from app.ai.providers import get_llm_provider
    from app.ai.research import get_research_backend
    from app.main import create_app
    from app.services.storage import reset_storage
    reset_storage()
    app = create_app()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    app.dependency_overrides[get_research_backend] = lambda: research
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@dataclass
class Account:
    user_id: uuid.UUID
    org_id: uuid.UUID
    token: str
    refresh: str
    email: str

    @property
    def h(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def signup(client):
    async def _signup(name: str = "Ada", product: str | None = "creator", email: str | None = None) -> Account:
        email = email or f"{name.lower().replace(' ', '-')}-{secrets.token_hex(3)}@example.com"
        r = await client.post("/v1/auth/signup", json={"email": email, "password": "correct-horse-battery",
                                                        "display_name": name, "country": "NG", "currency": "NGN",
                                                        "product": product})
        assert r.status_code == 201, r.text
        b = r.json()
        return Account(uuid.UUID(b["user"]["id"]), uuid.UUID(b["personal_org_id"]), b["tokens"]["access_token"],
                       b["tokens"]["refresh_token"], email)
    return _signup


@pytest.fixture
def make_workspace(client):
    async def _mk(acct: Account, name: str = "Lagos Coffee Co.", product: str = "creator", org_id=None) -> str:
        r = await client.post(f"/v1/orgs/{org_id or acct.org_id}/workspaces", json={"name": name, "product": product},
                              headers=acct.h)
        assert r.status_code == 201, r.text
        return r.json()["id"]
    return _mk


@pytest.fixture
def activate_plan(owner_db):
    """Give an org a paid plan through the same service the payment webhook uses."""
    async def _act(org_id, plan="pro", days=30, now=None):
        from app.core.db import transaction
        from app.services import subscriptions
        async with transaction(None, context="system") as s:
            await subscriptions.activate_period(s, org_id=org_id, plan_code=plan, provider="manual",
                                                provider_ref=f"test-{secrets.token_hex(4)}", days=days,
                                                auto_renew=False, now=now)
    return _act


from tests.helpers import (  # noqa: E402,F401  (re-exported for older imports)
    PDF_BYTES,
    pdf_file,
)
