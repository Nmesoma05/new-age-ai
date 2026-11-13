"""TEST-ONLY server for browser end-to-end runs (eco-web/e2e). Never deploy this.

Real FastAPI app, real Postgres (fresh database `eco_e2e`, migrated), real RLS, real files and retrieval.
Stand-ins: the external LLM (ScriptedProvider defaults, tests/ai/scripted.py) and the external integration
providers (Google/YouTube, Remotive, ExchangeRate-API), served by the same MockTransport fakes the pytest suite
uses (tests/integrations/conftest.py). In this mode an OAuth `code` of the form "e2e:<code_challenge>" stands for
"the user clicked Allow"; the PKCE verifier is still checked against that challenge.

    python -m tests.e2e_server            # serves http://127.0.0.1:8000
    python -m tests.e2e_server activate <org_id> <plan>   # give an org a paid plan, as the payment webhook would
"""
import asyncio
import os
import secrets
import sys

HOST = os.environ.get("TEST_PG_HOST", "localhost")
OWNER, OWNER_PW = os.environ.get("TEST_PG_OWNER", "eco_owner"), os.environ.get("TEST_PG_OWNER_PASSWORD", "owner_dev_pw")
APP, APP_PW = os.environ.get("TEST_PG_APP", "eco_app"), os.environ.get("TEST_PG_APP_PASSWORD", "app_dev_pw")
DB = "eco_e2e"

if os.environ.get("ENV") == "prod":
    sys.exit("refusing to run the test server with ENV=prod")

from cryptography.fernet import Fernet  # noqa: E402

os.environ.update({
    "ENV": "test",
    "DATABASE_URL": f"postgresql+psycopg://{APP}:{APP_PW}@{HOST}/{DB}",
    "MIGRATIONS_DATABASE_URL": f"postgresql+psycopg://{OWNER}:{OWNER_PW}@{HOST}/{DB}",
    "JWT_SECRET": os.environ.get("E2E_JWT_SECRET", secrets.token_urlsafe(48)),
    "CREDENTIALS_ENCRYPTION_KEY": os.environ.get("E2E_FERNET", Fernet.generate_key().decode()),
    "FILE_SCANNER": "disabled_dev_only",
    "STORAGE_LOCAL_DIR": "/tmp/eco-e2e-storage",
    "AI_RATE_LIMIT_PER_MINUTE": "1000",
    "EMBEDDING_PROVIDER": "hash_dev_only",
    "CORS_ORIGINS": '["http://localhost:3000"]',
    "GOOGLE_OAUTH_CLIENT_ID": "e2e-client.apps.googleusercontent.com",
    "GOOGLE_OAUTH_CLIENT_SECRET": "e2e-secret",
    "EMAIL_BACKEND": "dev_outbox",  # captured in email_outbox, never sent
    "OUTBOUND_HTTP_ENABLED": "true",  # only to the fakes: a transport is injected below
})


def fresh_db():
    import psycopg
    from alembic import command
    from alembic.config import Config
    with psycopg.connect(f"postgresql://{OWNER}:{OWNER_PW}@{HOST}/postgres", autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{DB}"')
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "migrations"))
    command.upgrade(cfg, "head")


async def activate(org_id: str, plan: str):
    from app.core.db import transaction
    from app.services import subscriptions
    async with transaction(None, context="system") as s:
        await subscriptions.activate_period(s, org_id=org_id, plan_code=plan, provider="manual",
                                            provider_ref=f"e2e-{secrets.token_hex(4)}", days=30, auto_renew=False)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "activate":
        asyncio.run(activate(sys.argv[2], sys.argv[3]))
        print("activated")
        return
    import httpx
    import uvicorn

    from app.ai.providers import get_llm_provider
    from app.integrations import http as ihttp
    from app.main import create_app
    from tests.ai.scripted import ScriptedProvider
    from tests.integrations.conftest import Fake
    fresh_db()
    fake = Fake()
    inner = fake.handler

    def handler(req):
        if req.url.path == "/token" and b"code=e2e%3A" in req.content:  # browser test's stand-in for consent
            from urllib.parse import parse_qs
            code = parse_qs(req.content.decode())["code"][0]
            fake.challenges[code] = code[4:]
        return inner(req)
    ihttp.set_transport(httpx.MockTransport(handler))
    app = create_app()
    provider = ScriptedProvider()
    app.dependency_overrides[get_llm_provider] = lambda: provider
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
