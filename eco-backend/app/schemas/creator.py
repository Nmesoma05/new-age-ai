"""Request/response models for the Creator & Marketing division."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ClientAccountIn, CreatorPlatform, Out

StudioKind = Literal["content", "brand_voice", "calendar", "campaign", "research", "report"]
CalendarStatus = Literal["planned", "drafted", "ready", "published_manually", "skipped"]
EditableCalendarStatus = Literal["planned", "drafted", "ready", "skipped"]
Url = Field(default=None, max_length=500, pattern=r"^https?://\S+$")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- onboarding & clients
class OnboardingIn(In):
    mode: Literal["solo", "agency"]
    agency_name: str | None = Field(default=None, min_length=1, max_length=120)
    client: ClientAccountIn

    @model_validator(mode="after")
    def _agency(self):
        if self.mode == "agency" and not self.agency_name:
            raise ValueError("agency_name is required for agency mode")
        return self


class NewClientIn(In):
    org_id: uuid.UUID
    client: ClientAccountIn


class ClientSummary(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    org_id: uuid.UUID
    org_name: str
    org_kind: str
    role: str
    client_name: str | None
    industry: str | None
    platforms: list[str]
    profile_complete: int  # 0-100
    created_at: datetime


class OnboardingState(BaseModel):
    has_creator_workspace: bool
    orgs: list[dict]
    clients: list[ClientSummary]
    next_step: Literal["create_first_client", "done"]


# ---------------------------------------------------------------- studio
class GenerateIn(In):
    kind: StudioKind
    brief: str = Field(min_length=3, max_length=4000)
    platforms: list[CreatorPlatform] = Field(default_factory=list, max_length=9)
    formats: list[str] = Field(default_factory=list, max_length=6)
    count: int | None = Field(default=None, ge=1, le=10)
    start_date: date | None = None
    end_date: date | None = None
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    save: bool = False

    @model_validator(mode="after")
    def _dates(self):
        needs = {"calendar": 92, "campaign": 366, "report": 366}
        if self.kind in needs:
            if not self.start_date or not self.end_date:
                raise ValueError(f"{self.kind} needs start_date and end_date")
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
            if (self.end_date - self.start_date).days > needs[self.kind]:
                raise ValueError(f"{self.kind} can cover at most {needs[self.kind]} days")
        return self


class SaveDraftsIn(In):
    indexes: list[int] | None = Field(default=None, max_length=10, description="Which drafts (0-based); all if omitted")
    campaign_id: uuid.UUID | None = None


class ApplyBrandIn(In):
    parts: list[Literal["voice", "personas", "pillars", "positioning"]] = Field(min_length=1, max_length=4)


class ImportCalendarIn(In):
    indexes: list[int] | None = Field(default=None, max_length=62)
    campaign_id: uuid.UUID | None = None


# ---------------------------------------------------------------- calendar
class CalendarItemIn(In):
    title: str = Field(min_length=1, max_length=200)
    platform: CreatorPlatform
    format: str = Field(default="post", min_length=1, max_length=40)
    scheduled_for: datetime
    pillar: str | None = Field(default=None, max_length=80)
    notes: str = Field(default="", max_length=4000)
    asset_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class CalendarItemPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    platform: CreatorPlatform | None = None
    format: str | None = Field(default=None, min_length=1, max_length=40)
    scheduled_for: datetime | None = None
    pillar: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)
    status: EditableCalendarStatus | None = None
    asset_id: uuid.UUID | None = None
    campaign_id: uuid.UUID | None = None


class MarkPublishedIn(In):
    published_url: str | None = Url
    published_at: datetime | None = None


class CalendarItemOut(Out):
    id: uuid.UUID
    campaign_id: uuid.UUID | None
    asset_id: uuid.UUID | None
    title: str
    platform: str
    format: str
    pillar: str | None
    notes: str
    scheduled_for: datetime
    status: str
    published_url: str | None
    published_at: datetime | None
    source: str
    created_at: datetime
    updated_at: datetime
    asset_title: str | None = None
    asset_status: str | None = None


# ---------------------------------------------------------------- campaigns
class CampaignIn(In):
    name: str = Field(min_length=1, max_length=160)
    objective: str = Field(default="", max_length=1000)
    status: Literal["draft", "active", "completed", "archived"] = "draft"
    start_date: date | None = None
    end_date: date | None = None
    channels: list[CreatorPlatform] = Field(default_factory=list, max_length=10)
    budget_note: str = Field(default="", max_length=1000)
    plan: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class CampaignPatch(In):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    objective: str | None = Field(default=None, max_length=1000)
    status: Literal["draft", "active", "completed", "archived"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    channels: list[CreatorPlatform] | None = Field(default=None, max_length=10)
    budget_note: str | None = Field(default=None, max_length=1000)
    plan: dict | None = None


class CampaignOut(Out):
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


class CampaignDetail(CampaignOut):
    calendar: list[CalendarItemOut] = []
    counts: dict[str, int] = {}


# ---------------------------------------------------------------- approvals
class SubmitIn(In):
    note: str = Field(default="", max_length=2000)


class DecisionIn(In):
    decision: Literal["approve", "request_changes"]
    comment: str = Field(default="", max_length=4000)


class CommentIn(In):
    body: str = Field(min_length=1, max_length=4000)


class CommentOut(Out):
    id: uuid.UUID
    asset_id: uuid.UUID
    asset_version: int
    kind: str
    body: str
    via: str
    author_user_id: uuid.UUID | None
    author_name: str | None
    created_at: datetime


class ReviewLinkIn(In):
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=120)
    expires_in_days: int = Field(default=7, ge=1, le=30)
    allow_approve: bool = True


class ReviewLinkOut(Out):
    id: uuid.UUID
    label: str
    asset_ids: list[uuid.UUID]
    allow_approve: bool
    expires_at: datetime
    revoked_at: datetime | None
    last_viewed_at: datetime | None
    created_at: datetime


class ReviewLinkCreated(ReviewLinkOut):
    token: str  # shown once; only its hash is stored


class PublicDecisionIn(In):
    decision: Literal["approve", "request_changes", "comment"]
    name: str = Field(min_length=1, max_length=120)
    comment: str = Field(default="", max_length=4000)


# ---------------------------------------------------------------- performance
class MetricIn(In):
    platform: CreatorPlatform
    post_label: str = Field(min_length=1, max_length=200)
    published_on: date
    post_url: str | None = Url
    calendar_item_id: uuid.UUID | None = None
    impressions: int | None = Field(default=None, ge=0)
    reach: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    clicks: int | None = Field(default=None, ge=0)
    video_views: int | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=1000)


class MetricOut(Out):
    id: uuid.UUID
    calendar_item_id: uuid.UUID | None
    platform: str
    post_label: str
    post_url: str | None
    published_on: date
    captured_on: date
    impressions: int | None
    reach: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    clicks: int | None
    video_views: int | None
    source: str
    notes: str
    created_at: datetime


class FollowersIn(In):
    platform: CreatorPlatform
    captured_on: date
    followers: int = Field(ge=0, le=10_000_000_000)


class FollowersOut(Out):
    id: uuid.UUID
    platform: str
    captured_on: date
    followers: int
    source: str
