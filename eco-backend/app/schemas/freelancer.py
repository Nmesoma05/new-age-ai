"""Request/response models for the Freelancer Growth division."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Out, ProfessionalProfileIn

Tool = Literal["assessment", "cv", "proposal", "interview", "portfolio", "brand", "outreach", "pricing", "learning",
               "opportunity"]
Market = Literal["global_remote", "us", "canada", "uk", "europe", "middle_east", "africa_local"]
_HTTP = r"^https?://\S+$"


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlOnboardingIn(In):
    profile: ProfessionalProfileIn


class RateFloorIn(In):
    income_goal_monthly: float = Field(gt=0, le=10_000_000)
    hours_per_week: float = Field(gt=0, le=80)
    monthly_costs: float = Field(default=0, ge=0, le=10_000_000)
    billable_share: float = Field(default=0.6, gt=0, le=1)
    tax_pct: float = Field(default=0, ge=0, lt=90)


class FlGenerateIn(In):
    tool: Tool
    brief: str = Field(default="", max_length=4000)
    job_text: str = Field(default="", max_length=20000, description="A pasted job post or brief (external data)")
    opportunity_id: uuid.UUID | None = None
    application_id: uuid.UUID | None = None
    target_role: str = Field(default="", max_length=150)
    market: Market = "global_remote"
    letter_type: Literal["proposal", "cover_letter", "pitch_message"] = "cover_letter"
    platforms: list[Literal["linkedin", "x", "instagram", "threads", "facebook", "tiktok"]] = Field(default_factory=list,
                                                                                                    max_length=6)
    weeks: int = Field(default=4, ge=1, le=26)
    hours_per_week: int | None = Field(default=None, ge=1, le=60)
    question_count: int = Field(default=6, ge=3, le=15)
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _needs(self):
        if self.tool == "opportunity" and not self.opportunity_id:
            raise ValueError("the opportunity check needs opportunity_id")
        return self


class SaveRunIn(In):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: uuid.UUID | None = None


class AssessmentIn(In):
    """The assessment as the user edits it (they can delete or rewrite anything)."""
    summary: str = Field(default="", max_length=900)
    stage_read: str = Field(default="", max_length=400)
    skills: list[dict] = Field(default_factory=list, max_length=20)
    strengths: list[str] = Field(default_factory=list, max_length=8)
    gaps: list[dict] = Field(default_factory=list, max_length=8)
    suggested_directions: list[dict] = Field(default_factory=list, max_length=6)
    headline_options: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("skills")
    @classmethod
    def _skills(cls, v):
        for s in v:
            if set(s) - {"skill", "evidence_level", "evidence_refs", "note"} or not str(s.get("skill", "")).strip():
                raise ValueError("each skill needs 'skill' and may have evidence_level, evidence_refs, note")
            if s.get("evidence_level", "stated") not in ("shown", "stated", "suggested"):
                raise ValueError("evidence_level must be shown, stated or suggested")
        return v


# ---------------------------------------------------------------- opportunities
OppKind = Literal["job", "freelance_project", "contract", "internship", "fellowship", "grant", "other"]
RemoteType = Literal["remote_global", "remote_regional", "hybrid", "onsite", "unknown"]
PayPeriod = Literal["hour", "day", "week", "month", "year", "project", "unknown"]


class TzRequirement(In):
    tz: str = Field(max_length=64)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)


def _codes(v: list[str]) -> list[str]:
    out = []
    for x in v:
        t = x.strip().upper().replace(" ", "_")
        if not t or len(t) > 20 or not t.replace("_", "").isalpha():
            raise ValueError("use 2-letter country codes or regions like EMEA, AFRICA, WORLDWIDE")
        out.append(t)
    return out


class OpportunityIn(In):
    kind: OppKind = "job"
    title: str = Field(min_length=1, max_length=200)
    organisation: str = Field(default="", max_length=200)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=2000)
    source_name: str = Field(default="", max_length=120)
    remote_type: RemoteType = "unknown"
    eligible_countries: list[str] = Field(default_factory=list, max_length=60)
    excluded_countries: list[str] = Field(default_factory=list, max_length=60)
    location_note: str = Field(default="", max_length=500)
    timezone_requirement: TzRequirement | None = None
    pay_min: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    pay_max: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    pay_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    pay_period: PayPeriod = "unknown"
    deadline: date | None = None
    description: str = Field(default="", max_length=20000)

    _c = field_validator("eligible_countries", "excluded_countries")(lambda cls, v: _codes(v))

    @model_validator(mode="after")
    def _pay(self):
        if self.pay_min is not None and self.pay_max is not None and self.pay_max < self.pay_min:
            raise ValueError("pay_max must be at least pay_min")
        if (self.pay_min is not None or self.pay_max is not None) and not self.pay_currency:
            raise ValueError("give a currency for the pay")
        if self.timezone_requirement:
            from app.services.freelancer import tz_ok
            if not tz_ok(self.timezone_requirement.tz):
                raise ValueError("unknown time zone in timezone_requirement")
        return self


class OpportunityPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    organisation: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=2000)
    remote_type: RemoteType | None = None
    eligible_countries: list[str] | None = Field(default=None, max_length=60)
    excluded_countries: list[str] | None = Field(default=None, max_length=60)
    deadline: date | None = None
    status: Literal["archived"] | None = None

    _c = field_validator("eligible_countries", "excluded_countries")(lambda cls, v: v if v is None else _codes(v))


class VerifyIn(In):
    still_open: bool
    note: str = Field(default="", max_length=500)


class OpportunityOut(Out):
    id: uuid.UUID
    kind: str
    title: str
    organisation: str
    url: str | None
    source: str
    source_name: str
    remote_type: str
    eligible_countries: list
    excluded_countries: list
    location_note: str
    timezone_requirement: dict
    pay_min: float | None
    pay_max: float | None
    pay_currency: str | None
    pay_period: str
    deadline: date | None
    description: str
    status: str
    verified_at: datetime | None
    verification_note: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- applications
AppStatus = Literal["preparing", "applied", "interviewing", "offer", "accepted", "rejected", "withdrawn", "no_response"]


class ApplicationIn(In):
    title: str = Field(min_length=1, max_length=200)
    organisation: str = Field(default="", max_length=200)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=2000)
    opportunity_id: uuid.UUID | None = None
    status: AppStatus = "preparing"
    applied_on: date | None = None
    next_step: str = Field(default="", max_length=300)
    next_step_due: date | None = None
    cv_asset_id: uuid.UUID | None = None
    letter_asset_id: uuid.UUID | None = None
    contact: str = Field(default="", max_length=200)
    expected_pay: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=4000)


class ApplicationPatch(In):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    organisation: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, pattern=_HTTP, max_length=2000)
    status: AppStatus | None = None
    status_note: str = Field(default="", max_length=300)
    applied_on: date | None = None
    next_step: str | None = Field(default=None, max_length=300)
    next_step_due: date | None = None
    cv_asset_id: uuid.UUID | None = None
    letter_asset_id: uuid.UUID | None = None
    contact: str | None = Field(default=None, max_length=200)
    expected_pay: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)


class ApplicationOut(Out):
    id: uuid.UUID
    opportunity_id: uuid.UUID | None
    title: str
    organisation: str
    url: str | None
    status: str
    applied_on: date | None
    next_step: str
    next_step_due: date | None
    cv_asset_id: uuid.UUID | None
    letter_asset_id: uuid.UUID | None
    contact: str
    expected_pay: str
    notes: str
    history: list
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- mock interviews
class InterviewIn(In):
    role_title: str = Field(min_length=1, max_length=200)
    application_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = Field(default=None, description="An interview-prep run to take questions from")
    questions: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def _src(self):
        if not self.run_id and not self.questions:
            raise ValueError("give an interview-prep run_id or your own questions")
        if any(not q.strip() or len(q) > 300 for q in self.questions):
            raise ValueError("questions must be 1-300 characters")
        return self


class AnswerIn(In):
    index: int = Field(ge=0, le=14)
    answer: str = Field(min_length=20, max_length=4000)


class InterviewOut(Out):
    id: uuid.UUID
    application_id: uuid.UUID | None
    role_title: str
    questions: list
    answers: list
    status: str
    created_at: datetime
    updated_at: datetime
