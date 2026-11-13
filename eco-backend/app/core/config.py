from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env that is never committed).

    Secrets are SecretStr so they never appear in logs or reprs. Nothing here is sent to the frontend.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "staging", "prod"] = "dev"  # staging gets every production guard
    database_url: SecretStr  # app role (eco_app), e.g. postgresql+psycopg://eco_app:...@host/eco
    db_pool_size: int = 10

    # Authentication
    auth_mode: Literal["local", "external_jwt"] = "local"
    jwt_secret: SecretStr = Field(..., min_length=32)
    jwt_issuer: str = "ecosystem-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    login_max_failures: int = 10
    login_lockout_minutes: int = 15
    # Per-IP limits on unauthenticated endpoints (0 = off). The client IP comes from X-Forwarded-For only via
    # TRUSTED_PROXIES (our web server, load balancer). JSON list of CIDRs.
    trusted_proxies: list[str] = ["127.0.0.1/32", "::1/128"]
    login_ip_max_failures: int = 30          # failed sign-ins per IP per 15 minutes
    signup_ip_per_hour: int = 10
    forgot_ip_per_hour: int = 10
    # external_jwt mode (e.g. Supabase Auth): verify tokens with the provider's JWKS
    external_jwks_url: str | None = None
    external_jwt_audience: str | None = None
    external_jwt_issuer: str | None = None

    # Secrets at rest. One Fernet key, or several comma-separated for rotation: the FIRST encrypts, all decrypt.
    credentials_encryption_key: SecretStr  # Fernet key(s) (urlsafe base64, 32 bytes each)

    # External integrations. Each provider is off until its credentials are configured; nothing here is sent to
    # the browser. The redirect URI registered with providers is f"{public_web_url}/integrations/callback".
    public_web_url: str = "http://localhost:3000"
    # Email delivery for account recovery. "none": password reset by email is reported as unavailable (never
    # pretends to send). "dev_outbox": messages are captured in the email_outbox table and NOT sent (dev/test only;
    # refused when env=prod). A real provider is a planned integration (docs/INTEGRATIONS.md, email_send).
    email_backend: Literal["none", "dev_outbox", "smtp"] = "none"
    # "smtp": any provider's SMTP relay (Postmark, Amazon SES, Brevo, Mailgun...). STARTTLS is required.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    email_from: str | None = None                # e.g. "New Age AI <no-reply@mail.example.com>" (a verified domain)
    password_reset_ttl_minutes: int = 30
    password_reset_max_per_hour: int = 3
    outbound_http_enabled: bool = True          # tests and air-gapped deploys set this to false
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    remotive_enabled: bool = True               # public API, no key; app-wide fetch cap enforced in code
    fx_provider_enabled: bool = True            # ExchangeRate-API open access (no key; attribution required)

    # Files
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = "./var/storage"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    max_upload_bytes: int = 20 * 1024 * 1024
    file_scanner: Literal["clamav", "disabled_dev_only"] = "clamav"
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    download_url_ttl_seconds: int = 900

    # AI: the provider is swappable (app/ai/providers). Model names and prices must be checked against the
    # provider's current docs and price page at deploy time; the defaults below are placeholders.
    ai_provider: Literal["openai", "anthropic"] = "openai"
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: SecretStr | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_version: str = "2023-06-01"
    ai_model: str = "gpt-4o-mini"          # "standard" tier: drafting agents
    ai_model_fast: str | None = None       # "fast" tier: router, summarizer (falls back to ai_model)
    ai_price_in_per_1m_usd: float = 0.0    # fallback price when a model isn't in ai_model_prices
    ai_price_out_per_1m_usd: float = 0.0
    ai_model_prices: dict[str, list[float]] = {}  # {"model": [usd_in_per_1M, usd_out_per_1M]}
    ai_timeout_seconds: float = 60.0
    ai_rate_limit_per_minute: int = 20
    fair_use_monthly_usd_per_user: float = 50.0
    ai_max_tool_steps: int = 6
    # Embeddings for retrieval. "hash_dev_only" is a local, low-quality embedder for dev and tests.
    embedding_provider: Literal["none", "openai", "hash_dev_only"] = "none"
    embedding_model: str = "text-embedding-3-small"  # must output embedding_dims; verify at deploy time
    embedding_dims: int = 1536
    # Web research backend for the researcher agent; none configured means research is reported unavailable.
    research_backend: Literal["none"] = "none"

    # Billing webhooks
    paystack_secret_key: SecretStr | None = None

    cors_origins: list[str] = []

    # Operations
    log_format: Literal["text", "json"] = "text"   # json in staging/prod (one line per event, no request bodies)
    sentry_dsn: SecretStr | None = None             # error tracking; PII is not sent
    release: str = "dev"                            # image tag / git SHA, set by the pipeline
    # AI cost control: when today's provider spend across ALL orgs reaches this, new generations pause with a clear
    # message until midnight UTC (0 = off). Per-user fair use still applies underneath.
    ai_daily_budget_usd: float = 0.0
    ai_budget_alert_ratio: float = 0.8              # log an alert once spend passes this share of the budget
    legal_terms_version: str | None = None          # version users accept at sign-up; required when deployed

    @property
    def is_deployed(self) -> bool:
        return self.env in ("staging", "prod")

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.is_deployed:
            # staging and production share every guard, so staging proves production's configuration
            pk = self.paystack_secret_key.get_secret_value() if self.paystack_secret_key else ""
            if self.env == "prod" and pk.startswith("sk_test_"):
                raise ValueError("a Paystack TEST key is configured in production")
            if self.env == "staging" and pk.startswith("sk_live_"):
                raise ValueError("a Paystack LIVE key is configured in staging")
            if self.storage_backend == "local":
                raise ValueError("deployed environments need STORAGE_BACKEND=s3 (container disks are not durable)")
            if self.email_backend != "smtp" or not (self.smtp_host and self.email_from and self.smtp_password):
                raise ValueError("deployed environments need EMAIL_BACKEND=smtp with SMTP_HOST, SMTP_PASSWORD and "
                                 "EMAIL_FROM (password reset must actually deliver)")
            if not self.public_web_url.startswith("https://") or any(not o.startswith("https://") for o in self.cors_origins):
                raise ValueError("PUBLIC_WEB_URL and CORS_ORIGINS must be https:// when deployed")
            if self.ai_daily_budget_usd <= 0:
                raise ValueError("set AI_DAILY_BUDGET_USD (a daily spend cap) when deployed")
            for m in {self.ai_model, self.ai_model_fast or self.ai_model}:
                price = self.ai_model_prices.get(m, [self.ai_price_in_per_1m_usd, self.ai_price_out_per_1m_usd])
                if len(price) != 2 or min(price) <= 0:
                    raise ValueError(f"set AI_MODEL_PRICES for {m}: with a $0 price, spend caps and fair use never "
                                     "trigger")
            if not self.legal_terms_version:
                raise ValueError("set LEGAL_TERMS_VERSION (the approved privacy policy/terms version) when deployed")
            if self.file_scanner == "disabled_dev_only":
                raise ValueError("file scanning cannot be disabled in production")
            if self.auth_mode == "external_jwt" and not (self.external_jwks_url and self.external_jwt_audience):
                raise ValueError("external_jwt mode needs EXTERNAL_JWKS_URL and EXTERNAL_JWT_AUDIENCE")
            if "*" in self.cors_origins:
                raise ValueError("wildcard CORS is not allowed in production")
            if self.embedding_provider == "hash_dev_only":
                raise ValueError("the hash embedder is for development only")
        if self.embedding_dims != 1536:
            raise ValueError("embedding_dims must match the vector(1536) columns in migration 0003")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
