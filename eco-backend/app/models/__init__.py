"""SQLAlchemy models. They mirror migrations/versions/*.py, which are the source of truth for DDL.

tests/test_migrations.py fails if a model column drifts from the migrated database.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import (
    ARRAY,
    BYTEA,
    CITEXT,
    INET,
    JSONB,
    TSVECTOR,
    UUID,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

PRODUCTS = ("creator", "business", "freelancer")
ORG_ROLES = ("owner", "admin", "member", "billing")
WS_ROLES = ("admin", "editor", "viewer", "client_approver")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _ts(nullable: bool = False, default: bool = True) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=nullable,
                         server_default=text("now()") if default else None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str | None] = mapped_column(String(3))
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="en")
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Africa/Lagos")
    email_verified_at: Mapped[datetime | None] = _ts(True, False)
    failed_logins: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until: Mapped[datetime | None] = _ts(True, False)
    password_changed_at: Mapped[datetime | None] = _ts(True, False)
    terms_version: Mapped[str | None] = mapped_column(Text)
    terms_accepted_at: Mapped[datetime | None] = _ts(True, False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    external_subject: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[datetime | None] = _ts(True, False)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = _ts(False, False)
    revoked_at: Mapped[datetime | None] = _ts(True, False)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[datetime | None] = _ts(True, False)


class OrgMember(Base):
    __tablename__ = "org_members"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts()


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts()


class TeamMember(Base):
    __tablename__ = "team_members"
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = _ts()


class ProductAccess(Base):
    __tablename__ = "product_access"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True)
    product: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = _ts()


class Plan(Base):
    __tablename__ = "plans"
    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ai_unlimited: Mapped[bool] = mapped_column(Boolean, nullable=False)
    free_monthly_limit: Mapped[int | None] = mapped_column(Integer)
    max_workspaces: Mapped[int] = mapped_column(Integer, nullable=False)
    max_seats: Mapped[int] = mapped_column(Integer, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(Text)
    period_start: Mapped[datetime] = _ts(False, False)
    period_end: Mapped[datetime] = _ts(False, False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    grace_until: Mapped[datetime | None] = _ts(True, False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True)
    period_month: Mapped[date] = mapped_column(Date, primary_key=True)
    free_generations_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[uuid.UUID] = _pk()
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    event_id: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = _ts()
    processed_at: Mapped[datetime | None] = _ts(True, False)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    product: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[datetime | None] = _ts(True, False)


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts()


class _WsScoped:
    """Columns every workspace-scoped row carries; (workspace_id, org_id) is a composite FK to workspaces."""
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class Project(_WsScoped, Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ClientAccount(_WsScoped, Base):
    __tablename__ = "client_accounts"
    id: Mapped[uuid.UUID] = _pk()
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(CITEXT)
    industry: Mapped[str | None] = mapped_column(Text)
    platforms: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    brand_voice: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    notes: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    business_info: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    audience: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    goals: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    competitors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    content_pillars: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class BusinessProfile(_WsScoped, Base):
    __tablename__ = "business_profiles"
    id: Mapped[uuid.UUID] = _pk()
    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str] = mapped_column(Text, nullable=False)
    sub_type: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    offers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    customers: Mapped[str | None] = mapped_column(Text)
    differentiators: Mapped[str | None] = mapped_column(Text)
    competitors: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    budget_band: Mapped[str | None] = mapped_column(Text)
    primary_goal: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False, server_default="other")
    stage: Mapped[str] = mapped_column(Text, nullable=False, server_default="growing")
    business_model: Mapped[str] = mapped_column(Text, nullable=False, server_default="b2c")
    target_markets: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    channels: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    goals: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    budget: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    brand: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    intelligence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    intelligence_updated_at: Mapped[datetime | None] = _ts(True, False)
    website: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class ProfessionalProfile(_WsScoped, Base):
    __tablename__ = "professional_profiles"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    headline: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    experiences: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    education: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    skills: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    rates: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    targets: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    full_name: Mapped[str | None] = mapped_column(Text)
    career_stage: Mapped[str] = mapped_column(Text, nullable=False, server_default="beginner")
    country: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(Text)
    work_modes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    interests: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    services: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    portfolio: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    certifications: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    languages: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    links: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    payment_methods: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    availability: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    assessment: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    assessment_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Document(_WsScoped, Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    text_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    created_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[datetime | None] = _ts(True, False)


class AiUsageRecord(Base):
    __tablename__ = "ai_usage_records"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    counted_free: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _ts()


class Conversation(_WsScoped, Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = _pk()
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="New conversation")
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    summary_through: Mapped[datetime | None] = _ts(True, False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Asset(_WsScoped, Base):
    __tablename__ = "assets"
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
    deleted_at: Mapped[datetime | None] = _ts(True, False)


class AssetVersion(_WsScoped, Base):
    __tablename__ = "asset_versions"
    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    source: Mapped[str] = mapped_column(Text, nullable=False)
    usage_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()


class Message(_WsScoped, Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    usage_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("clock_timestamp()"))


class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="connected")
    account_label: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    encrypted_credentials: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    auth_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="oauth2")
    external_account_id: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthAttempt(Base):
    """Per-IP attempt counter for sign-in/sign-up/reset limits (written by app.core.ratelimit)."""
    __tablename__ = "auth_attempts"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    ip: Mapped[str] = mapped_column(INET, nullable=False)
    at: Mapped[datetime] = _ts()


class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    to_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="captured_dev")
    created_at: Mapped[datetime] = _ts()


class OAuthState(Base):
    __tablename__ = "oauth_states"
    id: Mapped[uuid.UUID] = _pk()
    state_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    encrypted_verifier: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    return_to: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _ts()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IntegrationCall(Base):
    __tablename__ = "integration_calls"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    integration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _ts()


class ExternalCache(Base):
    __tablename__ = "external_cache"
    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organisations.id", ondelete="SET NULL"))
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text)
    target_id: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


# ---------------------------------------------------------------- AI engine (migration 0003)
class Vector(UserDefinedType):
    """pgvector column. Values are bound as the text form '[x,y,...]' so no extra driver package is needed."""
    cache_ok = True

    def __init__(self, dims: int):
        self.dims = dims

    def get_col_spec(self, **kw) -> str:
        return f"vector({self.dims})"

    def bind_processor(self, dialect):
        return lambda v: None if v is None else "[" + ",".join(f"{x:.7g}" for x in v) + "]"

    def result_processor(self, dialect, coltype):
        return lambda v: None if v is None else [float(x) for x in v.strip("[]").split(",") if x]


class AgentRun(_WsScoped, Base):
    __tablename__ = "agent_runs"
    id: Mapped[uuid.UUID] = _pk()
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    output: Mapped[dict | None] = mapped_column(JSONB)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    uncertainties: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    tainted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    injection_flags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    error_code: Mapped[str | None] = mapped_column(Text)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    counted_free: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = _ts()


class ToolCallRecord(_WsScoped, Base):
    __tablename__ = "tool_calls"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    args: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text)
    untrusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    result_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("clock_timestamp()"))


class MemoryItem(_WsScoped, Base):
    __tablename__ = "memory_items"
    id: Mapped[uuid.UUID] = _pk()
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="workspace")
    owner_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, Computed("to_tsvector('simple', content)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    last_used_at: Mapped[datetime | None] = _ts(True, False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class DocumentChunk(_WsScoped, Base):
    __tablename__ = "document_chunks"
    id: Mapped[uuid.UUID] = _pk()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tsv: Mapped[str | None] = mapped_column(TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _ts()


class PendingAction(_WsScoped, Base):
    __tablename__ = "pending_actions"
    id: Mapped[uuid.UUID] = _pk()
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    integration_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="awaiting_approval")
    from_untrusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = _ts(True, False)
    executed_at: Mapped[datetime | None] = _ts(True, False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("now() + interval '7 days'"))
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


# ---------------------------------------------------------------- Creator & Marketing division (migration 0004)
class Campaign(_WsScoped, Base):
    __tablename__ = "campaigns"
    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    channels: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    budget_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class CalendarItem(_WsScoped, Base):
    __tablename__ = "calendar_items"
    id: Mapped[uuid.UUID] = _pk()
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(Text, nullable=False, server_default="post")
    pillar: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="planned")
    published_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = _ts(True, False)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class AssetComment(_WsScoped, Base):
    __tablename__ = "asset_comments"
    id: Mapped[uuid.UUID] = _pk()
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    asset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    via: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    author_name: Mapped[str | None] = mapped_column(Text)
    review_link_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("review_links.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
                                                 server_default=text("clock_timestamp()"))


class ReviewLink(_WsScoped, Base):
    __tablename__ = "review_links"
    id: Mapped[uuid.UUID] = _pk()
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    asset_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    allow_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = _ts(True, False)
    last_viewed_at: Mapped[datetime | None] = _ts(True, False)
    created_at: Mapped[datetime] = _ts()


class PostMetric(_WsScoped, Base):
    __tablename__ = "post_metrics"
    id: Mapped[uuid.UUID] = _pk()
    calendar_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    post_url: Mapped[str | None] = mapped_column(Text)
    post_label: Mapped[str] = mapped_column(Text, nullable=False)
    published_on: Mapped[date] = mapped_column(Date, nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("current_date"))
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    reach: Mapped[int | None] = mapped_column(BigInteger)
    likes: Mapped[int | None] = mapped_column(BigInteger)
    comments: Mapped[int | None] = mapped_column(BigInteger)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    saves: Mapped[int | None] = mapped_column(BigInteger)
    clicks: Mapped[int | None] = mapped_column(BigInteger)
    video_views: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()


class FollowerSnapshot(_WsScoped, Base):
    __tablename__ = "follower_snapshots"
    id: Mapped[uuid.UUID] = _pk()
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    followers: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()


# ---------------------------------------------------------------- Business Marketing division (migration 0005)
class MarketingResult(_WsScoped, Base):
    __tablename__ = "marketing_results"
    id: Mapped[uuid.UUID] = _pk()
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    spend: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    impressions: Mapped[int | None] = mapped_column(BigInteger)
    clicks: Mapped[int | None] = mapped_column(BigInteger)
    leads: Mapped[int | None] = mapped_column(BigInteger)
    customers: Mapped[int | None] = mapped_column(BigInteger)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()


class Opportunity(_WsScoped, Base):
    __tablename__ = "opportunities"
    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    organisation: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    url: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    remote_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    eligible_countries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    excluded_countries: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    location_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    timezone_requirement: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    pay_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    pay_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    pay_currency: Mapped[str | None] = mapped_column(Text)
    pay_period: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    deadline: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unverified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verification_note: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class Application(_WsScoped, Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = _pk()
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    organisation: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="preparing")
    applied_on: Mapped[date | None] = mapped_column(Date)
    next_step: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    next_step_due: Mapped[date | None] = mapped_column(Date)
    cv_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    letter_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    contact: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    expected_pay: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    history: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()


class InterviewSession(_WsScoped, Base):
    __tablename__ = "interview_sessions"
    id: Mapped[uuid.UUID] = _pk()
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    role_title: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    answers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts()
