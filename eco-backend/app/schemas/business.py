"""Request/response models for the Business Marketing division."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import BusinessChannel, BusinessProfileIn, Out

Tool = Literal["intelligence", "positioning", "market", "competitors", "plan", "content", "ads", "acquisition",
               "retention", "report"]
SocialPlatform = Literal["instagram", "x", "linkedin", "tiktok", "facebook", "youtube", "threads", "whatsapp", "pinterest"]
Currency = Field(pattern=r"^[A-Z]{3}$")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- onboarding & businesses
class BizOnboardingIn(In):
    mode: Literal["solo", "team"]
    team_name: str | None = Field(default=None, min_length=1, max_length=120)
    profile: BusinessProfileIn

    @model_validator(mode="after")
    def _team(self):
        if self.mode == "team" and not self.team_name:
            raise ValueError("team_name is required for team mode")
        return self


class NewBusinessIn(In):
    org_id: uuid.UUID
    profile: BusinessProfileIn


class BusinessSummary(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    org_id: uuid.UUID
    org_name: str
    org_kind: str
    role: str
    business_name: str | None
    category: str | None
    stage: str | None
    location: str | None
    profile_complete: int
    has_intelligence: bool
    created_at: datetime


# ---------------------------------------------------------------- generation
class BizGenerateIn(In):
    tool: Tool
    brief: str = Field(default="", max_length=4000)
    plan_months: int | None = Field(default=None, ge=1, le=12)
    platforms: list[SocialPlatform] = Field(default_factory=list, max_length=6)
    start_date: date | None = None
    end_date: date | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _dates(self):
        if self.tool in ("ads", "report"):
            if not self.start_date or not self.end_date:
                raise ValueError(f"{self.tool} needs start_date and end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
            if (self.end_date - self.start_date).days > 366:
                raise ValueError("a date range can cover at most 366 days")
        return self


class SaveRunIn(In):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: uuid.UUID | None = None


class ApplyPositioningIn(In):
    parts: list[Literal["positioning", "messages", "voice", "visual"]] = Field(min_length=1)


# The Marketing Intelligence Profile, as people edit it (looser than the AI's output: you can delete sections).
class _Seg(In):
    name: str = Field(max_length=80)
    description: str = Field(default="", max_length=500)
    needs: list[str] = Field(default_factory=list, max_length=6)
    buying_triggers: list[str] = Field(default_factory=list, max_length=5)
    where_to_reach: list[BusinessChannel] = Field(default_factory=list, max_length=6)


class _Comp(In):
    competitor: str = Field(max_length=120)
    what_we_know: str = Field(default="", max_length=400)
    how_to_stand_out: str = Field(default="", max_length=400)


class _Fit(In):
    channel: BusinessChannel
    fit: Literal["strong", "possible", "weak"]
    why: str = Field(default="", max_length=300)


class IntelligenceIn(In):
    summary: str = Field(default="", max_length=900)
    stage_assessment: str = Field(default="", max_length=500)
    positioning_statement: str = Field(default="", max_length=400)
    value_proposition: str = Field(default="", max_length=400)
    customer_segments: list[_Seg] = Field(default_factory=list, max_length=6)
    competitive_landscape: list[_Comp] = Field(default_factory=list, max_length=10)
    channel_fit: list[_Fit] = Field(default_factory=list, max_length=21)
    priorities: list[str] = Field(default_factory=list, max_length=8)
    risks: list[str] = Field(default_factory=list, max_length=8)
    data_gaps: list[str] = Field(default_factory=list, max_length=8)


# ---------------------------------------------------------------- approvals (external actions)
class ApprovalRequestIn(In):
    kind: Literal["spend_money", "send_message"]
    run_id: uuid.UUID | None = None
    asset_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    channel: BusinessChannel | None = None
    audience: str = Field(default="", max_length=500)
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _shape(self):
        if (self.run_id is None) == (self.asset_id is None):
            raise ValueError("give exactly one of run_id or asset_id")
        if self.kind == "spend_money" and (self.amount is None or not self.currency):
            raise ValueError("spending needs an amount and currency")
        if self.kind == "send_message" and self.channel not in ("email", "sms", "whatsapp"):
            raise ValueError("send_message needs channel email, sms or whatsapp")
        return self


# ---------------------------------------------------------------- campaigns
class BizCampaignIn(In):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(default="", max_length=1000)
    status: Literal["draft", "active", "completed", "archived"] = "draft"
    start_date: date | None = None
    end_date: date | None = None
    channels: list[BusinessChannel] = Field(default_factory=list, max_length=10)
    budget_note: str = Field(default="", max_length=1000)
    plan: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class BizCampaignPatch(In):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    objective: str | None = Field(default=None, max_length=1000)
    status: Literal["draft", "active", "completed", "archived"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    channels: list[BusinessChannel] | None = Field(default=None, max_length=10)
    budget_note: str | None = Field(default=None, max_length=1000)


class BizCampaignOut(Out):
    id: uuid.UUID
    name: str
    objective: str
    status: str
    start_date: date | None
    end_date: date | None
    channels: list[str]
    budget_note: str
    plan: dict
    source_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- results
class ResultIn(In):
    channel: BusinessChannel
    campaign_id: uuid.UUID | None = None
    period_start: date
    period_end: date
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    spend: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    impressions: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    leads: int | None = Field(default=None, ge=0)
    customers: int | None = Field(default=None, ge=0)
    revenue: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _check(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        if all(getattr(self, m) is None for m in ("spend", "impressions", "clicks", "leads", "customers", "revenue")):
            raise ValueError("record at least one figure")
        return self


class ResultOut(Out):
    id: uuid.UUID
    channel: str
    campaign_id: uuid.UUID | None
    period_start: date
    period_end: date
    currency: str
    spend: float | None
    impressions: int | None
    clicks: int | None
    leads: int | None
    customers: int | None
    revenue: float | None
    source: str
    notes: str
    created_at: datetime
