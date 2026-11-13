from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

Product = Literal["creator", "business", "freelancer"]
OrgRole = Literal["owner", "admin", "member", "billing"]
WsRole = Literal["admin", "editor", "viewer", "client_approver"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    product: Product | None = None
    accept_terms: bool = False  # required when LEGAL_TERMS_VERSION is set (every deployed environment)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=200)


class TokensOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str


class UserOut(Out):
    id: uuid.UUID
    email: str
    display_name: str
    country: str | None
    currency: str | None
    locale: str
    timezone: str
    created_at: datetime


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=10, max_length=128)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    locale: str | None = Field(default=None, max_length=20)
    timezone: str | None = Field(default=None, max_length=64)


class SignupOut(BaseModel):
    user: UserOut
    personal_org_id: uuid.UUID
    tokens: TokensOut


# ---------------------------------------------------------------- organisations
class OrgIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class OrgOut(Out):
    id: uuid.UUID
    name: str
    kind: str
    owner_user_id: uuid.UUID
    created_at: datetime


class OrgWithRole(OrgOut):
    role: str


class MemberIn(BaseModel):
    email: EmailStr
    role: Literal["admin", "member", "billing"]


class MemberPatch(BaseModel):
    role: Literal["admin", "member", "billing"]


class MemberOut(BaseModel):
    user_id: uuid.UUID
    display_name: str
    email: str
    role: str


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TeamOut(Out):
    id: uuid.UUID
    name: str
    created_at: datetime


class TeamMemberIn(BaseModel):
    user_id: uuid.UUID


class ProductIn(BaseModel):
    product: Product


class ProductOut(Out):
    product: str
    status: str


# ---------------------------------------------------------------- workspaces
class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    product: Product


class WorkspacePatch(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceOut(Out):
    id: uuid.UUID
    org_id: uuid.UUID
    product: str
    name: str
    created_at: datetime


class WorkspaceWithRole(WorkspaceOut):
    role: str
    read_only: bool = False


class WsMemberIn(BaseModel):
    user_id: uuid.UUID
    role: WsRole


class WsMemberPatch(BaseModel):
    role: WsRole


class WsMemberOut(BaseModel):
    user_id: uuid.UUID
    role: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None


class ProjectOut(Out):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime


# ---------------------------------------------------------------- profiles
CreatorPlatform = Literal["instagram", "x", "linkedin", "tiktok", "facebook", "youtube", "threads", "whatsapp",
                          "pinterest", "other"]


class _Sub(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Offer(_Sub):
    name: str = Field(min_length=1, max_length=120)
    price: str | None = Field(default=None, max_length=60, description="As the client states it, e.g. 'NGN 4,500'")
    description: str | None = Field(default=None, max_length=500)


class BusinessInfo(_Sub):
    description: str = Field(default="", max_length=2000)
    offers: list[Offer] = Field(default_factory=list, max_length=30)
    location: str = Field(default="", max_length=200)


class AudiencePersona(_Sub):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)
    needs: list[str] = Field(default_factory=list, max_length=8)
    where_they_spend_time: list[str] = Field(default_factory=list, max_length=8)


class Audience(_Sub):
    summary: str = Field(default="", max_length=2000)
    personas: list[AudiencePersona] = Field(default_factory=list, max_length=6)
    locations: list[str] = Field(default_factory=list, max_length=10)


class Goal(_Sub):
    goal: str = Field(min_length=1, max_length=300)
    metric: str = Field(default="", max_length=120)
    due: date | None = None


class Competitor(_Sub):
    name: str = Field(min_length=1, max_length=120)
    handle: str = Field(default="", max_length=120)
    platform: CreatorPlatform | None = None
    notes: str = Field(default="", max_length=2000, description="What the team has observed, entered by hand")


class ContentPillar(_Sub):
    name: str = Field(min_length=1, max_length=60)
    purpose: str = Field(default="", max_length=300)
    example_topics: list[str] = Field(default_factory=list, max_length=8)


class ClientAccountIn(BaseModel):
    client_name: str = Field(min_length=1, max_length=120)
    contact_email: EmailStr | None = None
    industry: str | None = Field(default=None, max_length=80)
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://\S+$")
    business_info: BusinessInfo = Field(default_factory=BusinessInfo)
    platforms: list[CreatorPlatform] = Field(default_factory=list, max_length=10)
    brand_voice: dict = Field(default_factory=dict, description="Voice traits, words to use/avoid, sample lines, "
                                                                "tone by platform")
    audience: Audience = Field(default_factory=Audience)
    goals: list[Goal] = Field(default_factory=list, max_length=10)
    competitors: list[Competitor] = Field(default_factory=list, max_length=10)
    content_pillars: list[ContentPillar] = Field(default_factory=list, max_length=8)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("brand_voice")
    @classmethod
    def _voice_size(cls, v: dict) -> dict:
        import json as _json
        if len(_json.dumps(v)) > 20_000:
            raise ValueError("brand_voice is too large")
        return v


class ClientAccountOut(ClientAccountIn, Out):
    id: uuid.UUID
    version: int
    updated_at: datetime


BusinessCategory = Literal["food_hospitality", "retail_ecommerce", "beauty_wellness", "professional_services",
                           "b2b_tech", "health_clinics", "education_training", "real_estate_construction",
                           "travel_events", "manufacturing_wholesale", "home_local_services", "creative_media",
                           "finance_fintech", "agriculture", "nonprofit", "other"]
BusinessChannel = Literal["instagram", "facebook", "tiktok", "x", "linkedin", "youtube", "whatsapp",
                          "google_search_ads", "meta_ads", "email", "sms", "website_seo", "google_business_profile",
                          "marketplaces", "referrals", "events", "partnerships", "print_outdoor", "radio_tv",
                          "sales_outreach", "other"]


class ChannelUse(_Sub):
    channel: BusinessChannel
    status: Literal["using", "tried", "considering"] = "using"
    notes: str = Field(default="", max_length=500)


class BusinessGoal(_Sub):
    goal: str = Field(min_length=1, max_length=300)
    metric: str = Field(default="", max_length=120)
    target: str = Field(default="", max_length=80, description="The owner's own target, as they state it")
    due: date | None = None


class Budget(_Sub):
    monthly_amount: float | None = Field(default=None, ge=0, le=1e12)
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    notes: str = Field(default="", max_length=500)


class BusinessCompetitor(_Sub):
    name: str = Field(min_length=1, max_length=120)
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://\S+$")
    notes: str = Field(default="", max_length=2000, description="What the owner has observed")


class BusinessProfileIn(BaseModel):
    business_name: str = Field(min_length=1, max_length=120)
    category: BusinessCategory = "other"
    industry: str = Field(min_length=1, max_length=80)
    sub_type: str | None = Field(default=None, max_length=80)
    stage: Literal["idea", "new", "growing", "established"] = "growing"
    business_model: Literal["b2c", "b2b", "both"] = "b2c"
    location: str | None = Field(default=None, max_length=200)
    target_markets: list[str] = Field(default_factory=list, max_length=10)
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://\S+$")
    offers: list[Offer] = Field(default_factory=list, max_length=50)
    customers: str | None = Field(default=None, max_length=2000)
    differentiators: str | None = Field(default=None, max_length=2000)
    competitors: list[BusinessCompetitor] = Field(default_factory=list, max_length=20)
    channels: list[ChannelUse] = Field(default_factory=list, max_length=21)
    goals: list[BusinessGoal] = Field(default_factory=list, max_length=8)
    budget: Budget = Field(default_factory=Budget)
    brand: dict = Field(default_factory=dict)
    budget_band: Literal["none", "low", "medium", "high"] | None = None
    primary_goal: Literal["awareness", "enquiries", "sales", "launch"] | None = None

    @field_validator("brand")
    @classmethod
    def _brand_size(cls, v: dict) -> dict:
        import json as _json
        if len(_json.dumps(v)) > 20_000:
            raise ValueError("brand is too large")
        return v


class BusinessProfileOut(BusinessProfileIn, Out):
    id: uuid.UUID
    version: int
    updated_at: datetime
    intelligence: dict = {}
    intelligence_updated_at: datetime | None = None


# ---------------------------------------------------------------- professional profile (Freelancer Growth)
CareerStage = Literal["beginner", "experienced_freelancer", "job_seeker", "consultant"]
WorkMode = Literal["freelance", "remote_full_time", "contract", "part_time", "internship"]
_HTTP = r"^https?://\S+$"


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Experience(_P):
    title: str = Field(min_length=1, max_length=150)
    organisation: str = Field(default="", max_length=150, description="Employer or client; may be 'Confidential client'")
    employment_type: Literal["freelance", "full_time", "part_time", "contract", "internship", "volunteer", "project",
                             "other"] = "other"
    period: str = Field(default="", max_length=60, description="As the user writes it, e.g. 'Mar 2022 - present'")
    location: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1500)
    achievements: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="before")
    @classmethod
    def _legacy(cls, v):  # older clients sent {role, company, years}
        if isinstance(v, dict):
            v = dict(v)
            for old, new in (("role", "title"), ("company", "organisation"), ("years", "period")):
                if old in v and new not in v:
                    v[new] = v.pop(old)
        return v


class Education(_P):
    qualification: str = Field(min_length=1, max_length=150)
    institution: str = Field(default="", max_length=150)
    period: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)


class SkillIn(_P):
    name: str = Field(min_length=1, max_length=80)
    level: Literal["learning", "beginner", "intermediate", "advanced", "expert"] | None = None
    years: str | None = Field(default=None, max_length=20)
    evidence: str = Field(default="", max_length=300, description="Where it was used or how it can be shown")


class ServiceIn(_P):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=600)
    deliverables: list[str] = Field(default_factory=list, max_length=10)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    pricing_model: Literal["fixed", "hourly", "daily", "retainer", "per_unit", "unknown"] = "unknown"


class PortfolioItem(_P):
    title: str = Field(min_length=1, max_length=150)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=500)
    description: str = Field(default="", max_length=1200)
    role: str = Field(default="", max_length=200)
    outcome: str = Field(default="", max_length=500, description="Only results the user can stand behind")


class Certification(_P):
    name: str = Field(min_length=1, max_length=150)
    issuer: str = Field(default="", max_length=150)
    year: str = Field(default="", max_length=10)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=500)


class LanguageIn(_P):
    language: str = Field(min_length=1, max_length=60)
    level: Literal["basic", "conversational", "professional", "fluent", "native"] = "professional"


class LinkIn(_P):
    label: str = Field(min_length=1, max_length=60)
    url: str = Field(pattern=_HTTP, max_length=500)


class Rates(_P):
    hourly: float | None = Field(default=None, ge=0)
    daily: float | None = Field(default=None, ge=0)
    monthly: float | None = Field(default=None, ge=0)
    project_minimum: float | None = Field(default=None, ge=0)
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    notes: str = Field(default="", max_length=500)


class Targets(_P):
    roles: list[str] = Field(default_factory=list, max_length=8)
    client_types: list[str] = Field(default_factory=list, max_length=8)
    markets: list[str] = Field(default_factory=list, max_length=10, description="Countries or regions to work with")
    income_goal_monthly: float | None = Field(default=None, ge=0)
    currency: str = Field(default="", pattern=r"^([A-Z]{3})?$")
    goals: list[str] = Field(default_factory=list, max_length=8)
    notes: str = Field(default="", max_length=800)


class Availability(_P):
    hours_per_week: int | None = Field(default=None, ge=1, le=80)
    start: str = Field(default="", max_length=60)
    working_hours: str = Field(default="", max_length=120, description="e.g. 09:00-18:00 local, flexible evenings")


class ProfessionalProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, max_length=120)
    headline: str | None = Field(default=None, max_length=200)
    summary: str | None = Field(default=None, max_length=3000)
    career_stage: CareerStage = "beginner"
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    city: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    work_modes: list[WorkMode] = Field(default_factory=list, max_length=5)
    interests: list[str] = Field(default_factory=list, max_length=15)
    experiences: list[Experience] = Field(default_factory=list, max_length=30)
    education: list[Education] = Field(default_factory=list, max_length=15)
    skills: list[SkillIn] = Field(default_factory=list, max_length=60)
    services: list[ServiceIn] = Field(default_factory=list, max_length=12)
    portfolio: list[PortfolioItem] = Field(default_factory=list, max_length=20)
    certifications: list[Certification] = Field(default_factory=list, max_length=20)
    languages: list[LanguageIn] = Field(default_factory=list, max_length=10)
    links: list[LinkIn] = Field(default_factory=list, max_length=10)
    payment_methods: list[str] = Field(default_factory=list, max_length=8)
    availability: Availability = Field(default_factory=Availability)
    rates: Rates = Field(default_factory=Rates)
    targets: Targets = Field(default_factory=Targets)

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is not None:
            from zoneinfo import available_timezones
            if v not in available_timezones():
                raise ValueError("unknown time zone; use an IANA name like Africa/Lagos")
        return v

    @field_validator("interests", "payment_methods")
    @classmethod
    def _short(cls, v):
        if any(len(x) > 80 or not x.strip() for x in v):
            raise ValueError("each entry must be 1-80 characters")
        return v

    def to_row(self) -> dict:
        """Column values; nested objects drop empty fields so the AI sees (and cites) only what the user filled in."""
        out = {}
        for k in type(self).model_fields:
            v = getattr(self, k)
            if isinstance(v, BaseModel):
                out[k] = v.model_dump(mode="json", exclude_none=True, exclude_defaults=True)
            elif isinstance(v, list):
                out[k] = [x.model_dump(mode="json", exclude_none=True, exclude_defaults=True) if isinstance(x, BaseModel)
                          else x for x in v]
            else:
                out[k] = v
        return out


class ProfessionalProfileOut(Out):
    id: uuid.UUID
    full_name: str | None
    headline: str | None
    summary: str | None
    career_stage: str
    country: str | None
    city: str | None
    timezone: str | None
    currency: str | None
    work_modes: list
    interests: list
    experiences: list
    education: list
    skills: list
    services: list
    portfolio: list
    certifications: list
    languages: list
    links: list
    payment_methods: list
    availability: dict
    rates: dict
    targets: dict
    assessment: dict
    assessment_updated_at: datetime | None
    version: int
    updated_at: datetime


# ---------------------------------------------------------------- documents
class DocumentOut(Out):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    scan_status: str
    text_status: str
    created_at: datetime


class DownloadUrlOut(BaseModel):
    url: str
    expires_at: datetime


# ---------------------------------------------------------------- conversations and assets
class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=200)


class ConversationOut(Out):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=8000)
    agent: str | None = Field(default=None, max_length=60,
                              description="Optional: pick a specialist instead of automatic routing")
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5,
                                          description="Documents in this workspace the request is about")
    save_as_asset: bool = False
    asset_type: Literal["post", "thread", "caption", "script", "campaign_plan", "content_plan", "report", "cv",
                        "proposal", "cover_letter", "case_study", "note", "other"] | None = None


class MessageOut(Out):
    id: uuid.UUID
    role: str
    content: str
    asset_id: uuid.UUID | None
    created_at: datetime


class PendingActionRef(BaseModel):
    id: uuid.UUID
    kind: str
    title: str


class RunSummaryOut(BaseModel):
    id: uuid.UUID
    agent: str
    status: Literal["succeeded", "failed", "clarify", "unsupported", "blocked"]
    output: dict | None = None
    warnings: list[str] = []
    uncertainties: list[str] = []
    injection_detected: bool = False
    pending_actions: list[PendingActionRef] = []
    saved_asset_id: uuid.UUID | None = None
    memory_saved: list[dict] = []


class ExchangeOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    run: RunSummaryOut | None = None


class ToolCallOut(Out):
    agent: str
    tool: str
    args: dict
    status: str
    error_code: str | None
    untrusted: bool
    result_meta: dict
    latency_ms: int
    created_at: datetime


class RunOut(Out):
    id: uuid.UUID
    conversation_id: uuid.UUID | None
    user_id: uuid.UUID
    agent: str
    status: str
    route: dict
    output: dict | None
    warnings: list
    uncertainties: list
    tainted: bool
    injection_flags: list
    error_code: str | None
    llm_calls: int
    tokens_in: int
    tokens_out: int
    counted_free: bool
    latency_ms: int
    created_at: datetime


class RunDetailOut(RunOut):
    tool_calls: list[ToolCallOut] = []


class PendingActionOut(Out):
    id: uuid.UUID
    run_id: uuid.UUID | None
    kind: str
    title: str
    payload: dict
    status: str
    from_untrusted: bool
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    executed_at: datetime | None
    result: dict
    expires_at: datetime
    created_at: datetime


class ActionDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


MemoryKind = Literal["fact", "preference", "decision", "brand_rule", "constraint"]


class MemoryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=3, max_length=1000)
    kind: MemoryKind = "fact"
    visibility: Literal["workspace", "private"] = "workspace"
    project_id: uuid.UUID | None = None


class MemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["active", "archived"] | None = None
    content: str | None = Field(default=None, min_length=3, max_length=1000)


class MemoryOut(Out):
    id: uuid.UUID
    kind: str
    content: str
    visibility: str
    source: str
    status: str
    owner_user_id: uuid.UUID
    project_id: uuid.UUID | None
    source_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


AssetType = Literal["post", "thread", "caption", "script", "campaign_plan", "content_plan", "report", "cv",
                    "proposal", "cover_letter", "case_study", "note", "other"]
AssetStatus = Literal["draft", "in_review", "approved", "posted", "archived"]


class AssetIn(BaseModel):
    type: AssetType
    title: str = Field(min_length=1, max_length=200)
    body: dict
    body_text: str = Field(default="", max_length=100_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    project_id: uuid.UUID | None = None

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [t.strip()[:40] for t in v if t.strip()]


class AssetPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: AssetStatus | None = None
    tags: list[str] | None = Field(default=None, max_length=20)


class AssetVersionIn(BaseModel):
    body: dict
    body_text: str = Field(default="", max_length=100_000)


class AssetOut(Out):
    id: uuid.UUID
    workspace_id: uuid.UUID
    project_id: uuid.UUID | None
    type: str
    title: str
    status: str
    current_version: int
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class AssetVersionOut(Out):
    id: uuid.UUID
    version: int
    body: dict
    body_text: str
    source: str
    author_id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------- billing, integrations, audit
class SubscriptionOut(BaseModel):
    plan: str
    plan_name: str
    ai_unlimited: bool
    status: str
    period_end: datetime | None
    auto_renew: bool | None
    max_workspaces: int
    max_seats: int


class UsageOut(BaseModel):
    plan: str
    ai_unlimited: bool
    free_monthly_limit: int | None
    free_used_this_month: int | None
    free_remaining: int | None


class IntegrationIn(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9_]{2,40}$")
    account_label: str | None = Field(default=None, max_length=120)
    scopes: list[str] = Field(default_factory=list, max_length=30)
    credentials: dict = Field(description="Write-only. Encrypted at rest and never returned.")
    workspace_id: uuid.UUID | None = None


class IntegrationOut(Out):
    id: uuid.UUID
    provider: str
    status: str
    account_label: str | None
    scopes: list[str]
    workspace_id: uuid.UUID | None
    created_at: datetime


class AuditOut(BaseModel):
    id: int
    action: str
    actor_user_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    metadata: dict
    created_at: datetime
