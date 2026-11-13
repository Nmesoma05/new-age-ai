"""The implemented providers. Each one maps provider data into our tables with source='integration' and enforces
the provider's own terms (fetch caps, attribution, delays) in code, not just in documentation.
"""
from __future__ import annotations

import asyncio
import html
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import transaction
from app.integrations import oauth
from app.integrations.http import (
    CallContext,
    IntegrationError,
    ProviderLimits,
    json_of,
    request,
)
from app.models import ExternalCache, FollowerSnapshot, Integration, PostMetric

# ====================================================================== shared public cache


async def cached(key: str) -> ExternalCache | None:
    async with transaction(None, context="system") as s:
        return await s.get(ExternalCache, key)


async def store(key: str, provider: str, payload: dict, ttl: timedelta, fetched_at: datetime | None = None) -> None:
    """Upsert: safe when two instances refresh the same key at once (QA BUG-01)."""
    now = fetched_at or datetime.now(UTC)
    vals = {"cache_key": key, "provider": provider, "payload": payload, "fetched_at": now, "expires_at": now + ttl}
    async with transaction(None, context="system") as s:
        stmt = pg_insert(ExternalCache).values(**vals)
        await s.execute(stmt.on_conflict_do_update(index_elements=["cache_key"], set_={
            k: stmt.excluded[k] for k in ("payload", "fetched_at", "expires_at")}))


_flights: dict[str, asyncio.Lock] = {}


def single_flight(key: str) -> asyncio.Lock:
    """One upstream fetch per cache key per process: concurrent misses wait and reuse the result instead of each
    calling the provider (which would also break Remotive's fetch cap)."""
    return _flights.setdefault(key, asyncio.Lock())


# ====================================================================== 1. exchange rates (ExchangeRate-API open)
FX_LIMITS = ProviderLimits(hosts=frozenset({"open.er-api.com"}), rate_per_sec=0.5, burst=2, max_attempts=2)
FX_ATTRIBUTION = {"text": "Rates By Exchange Rate API", "url": "https://www.exchangerate-api.com"}
FX_TTL = timedelta(hours=12)  # provider updates daily and asks for at most hourly requests


async def fx_rates(session: AsyncSession, base: str) -> dict:
    """Today's rates for `base` (cached app-wide). Raises IntegrationError if unavailable."""
    if not get_settings().fx_provider_enabled:
        raise IntegrationError("not_configured", "Currency conversion is switched off on this server.")
    base = base.upper()
    if not re.fullmatch(r"[A-Z]{3}", base):
        raise IntegrationError("bad_currency", "Use a 3-letter currency code.")
    key = f"fx:{base}"
    hit = await cached(key)
    if hit and hit.expires_at > datetime.now(UTC):
        return hit.payload
    async with single_flight(key):
        hit = await cached(key)  # someone may have refreshed it while we waited
        if hit and hit.expires_at > datetime.now(UTC):
            return hit.payload
        return await _fetch_fx(session, base, key, hit)


async def _fetch_fx(session: AsyncSession, base: str, key: str, hit: ExternalCache | None) -> dict:
    try:
        resp = await request(CallContext(session, "fx_exchangerate_api", "fx.latest"), FX_LIMITS, "GET",
                             f"https://open.er-api.com/v6/latest/{base}")
        body = json_of(resp)
        if body.get("result") != "success" or not isinstance(body.get("rates"), dict):
            raise IntegrationError("bad_response", "The rates service didn't return rates for that currency.")
    except IntegrationError:
        if hit:  # serve yesterday's rates rather than nothing, clearly dated
            return {**hit.payload, "stale": True}
        raise
    payload = {"base": base, "rates": {k: v for k, v in body["rates"].items() if isinstance(v, (int, float))},
               "updated": body.get("time_last_update_utc"), "next_update": body.get("time_next_update_utc"),
               "attribution": FX_ATTRIBUTION, "stale": False}
    await store(key, "fx_exchangerate_api", payload, FX_TTL)
    return payload


async def convert(session: AsyncSession, amount: Decimal, frm: str, to: str) -> dict:
    rates = await fx_rates(session, frm)
    rate = rates["rates"].get(to.upper())
    if rate is None:
        raise IntegrationError("unsupported_currency", f"No rate available for {to.upper()}.")
    return {"amount": float(amount), "from": frm.upper(), "to": to.upper(), "rate": rate,
            "converted": round(float(amount) * rate, 2), "rates_updated": rates["updated"], "stale": rates["stale"],
            "attribution": FX_ATTRIBUTION,
            "note": "Indicative daily reference rate, not what a bank or payment provider will pay out."}


# ====================================================================== 2. Remotive public job feed
REMOTIVE_LIMITS = ProviderLimits(hosts=frozenset({"remotive.com"}), rate_per_sec=1 / 40, burst=1, max_attempts=2,
                                 base_delay=2.0)
REMOTIVE_TTL = timedelta(hours=6)  # terms: fetch no more than ~4 times a day (app-wide)
REMOTIVE_ATTRIBUTION = {"text": "Jobs from Remotive", "url": "https://remotive.com",
                        "terms": "Listings are delayed 24 hours. Apply on Remotive's page for each job."}


def _strip_html(s: str) -> str:
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s or "", flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"[ \t]+", " ", html.unescape(s)).strip()


async def remotive_feed(session: AsyncSession) -> dict:
    """The whole public feed, fetched at most every 6 hours for the entire app (one shared snapshot)."""
    if not get_settings().remotive_enabled:
        raise IntegrationError("not_configured", "The Remotive job feed is switched off on this server.")
    hit = await cached("remotive:all")
    if hit and hit.expires_at > datetime.now(UTC):
        return hit.payload
    async with single_flight("remotive:all"):
        hit = await cached("remotive:all")
        if hit and hit.expires_at > datetime.now(UTC):
            return hit.payload
        return await _fetch_remotive(session, hit)


async def _fetch_remotive(session: AsyncSession, hit: ExternalCache | None) -> dict:
    try:
        resp = await request(CallContext(session, "remotive", "remotive.jobs"), REMOTIVE_LIMITS, "GET",
                             "https://remotive.com/api/remote-jobs", timeout=30.0)
        body = json_of(resp)
        jobs = body.get("jobs")
        if not isinstance(jobs, list):
            raise IntegrationError("bad_response", "The job feed returned something unexpected.")
    except IntegrationError:
        if hit:
            return {**hit.payload, "stale": True}
        raise
    items = []
    for j in jobs[:2000]:
        url = str(j.get("url") or "")
        if not url.startswith("https://remotive.com/"):
            continue  # only link back to Remotive itself, as its terms require
        items.append({"id": str(j.get("id")), "url": url, "title": str(j.get("title") or "")[:200],
                      "company": str(j.get("company_name") or "")[:200], "category": str(j.get("category") or ""),
                      "job_type": str(j.get("job_type") or ""), "published": str(j.get("publication_date") or ""),
                      "location": str(j.get("candidate_required_location") or "")[:300],
                      "salary": str(j.get("salary") or "")[:120],
                      "description": _strip_html(str(j.get("description") or ""))[:19000]})
    payload = {"jobs": items, "fetched_at": datetime.now(UTC).isoformat(), "attribution": REMOTIVE_ATTRIBUTION,
               "stale": False}
    await store("remotive:all", "remotive", payload, REMOTIVE_TTL)
    return payload


def search_jobs(feed: dict, q: str = "", category: str = "", limit: int = 30) -> list[dict]:
    words = [w for w in re.findall(r"\w+", q.lower()) if len(w) > 1]
    out = []
    for j in feed["jobs"]:
        if category and j["category"].lower() != category.lower():
            continue
        hay = f"{j['title']} {j['company']} {j['category']} {j['description'][:2000]}".lower()
        if all(w in hay for w in words):
            out.append({k: v for k, v in j.items() if k != "description"} | {"snippet": j["description"][:300]})
        if len(out) >= limit:
            break
    return out


_WORLD = re.compile(r"\b(worldwide|anywhere|global)\b", re.I)


def location_to_codes(loc: str) -> tuple[str, list[str]]:
    """Map Remotive's free-text 'candidate_required_location' to our remote_type + location tokens. Parts we can't
    recognise are left out (the raw text is kept in location_note) and eligibility then says 'unclear': we never
    guess."""
    from app.services.freelancer import COUNTRIES, REGIONS
    if not loc:
        return "unknown", []
    if _WORLD.search(loc):
        return "remote_global", ["WORLDWIDE"]
    names = {v["name"].upper(): c for c, v in COUNTRIES.items()}
    alias = {"USA": "US", "UNITED STATES": "US", "U.S.": "US", "UK": "GB", "LATIN AMERICA": "LATAM",
             "MIDDLE EAST": "MIDDLE_EAST", "EUROPEAN UNION": "EU"}
    tokens: list[str] = []
    for part in re.split(r"[,/;|]| or | and ", loc):
        p = re.sub(r"\s+ONLY$", "", re.sub(r"\s*\(.*?\)\s*", " ", part).strip().upper()).strip()
        code = alias.get(p) or names.get(p) or (p if p in REGIONS or p in COUNTRIES else None)
        if code and code not in tokens:
            tokens.append(code)
    return ("remote_regional", tokens) if tokens else ("unknown", [])


# ====================================================================== 3. YouTube analytics (read-only)
YT_SCOPES = ("https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/yt-analytics.readonly")
YT_LIMITS = ProviderLimits(hosts=frozenset({"www.googleapis.com", "youtubeanalytics.googleapis.com"}),
                           rate_per_sec=3, burst=6)


async def youtube_identity(session: AsyncSession, token: str, org_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    ctx = CallContext(session, "youtube", "youtube.channels.mine", org_id=org_id, workspace_id=workspace_id)
    body = json_of(await request(ctx, YT_LIMITS, "GET", "https://www.googleapis.com/youtube/v3/channels",
                                 headers={"Authorization": f"Bearer {token}"},
                                 params={"part": "snippet,statistics", "mine": "true"}))
    items = body.get("items") or []
    if not items:
        raise IntegrationError("no_channel", "That Google account has no YouTube channel.")
    ch = items[0]
    return {"id": ch["id"], "title": ch["snippet"]["title"],
            "subscribers": None if ch["statistics"].get("hiddenSubscriberCount")
            else int(ch["statistics"].get("subscriberCount", 0))}


async def youtube_sync(session: AsyncSession, integ: Integration, user_id: uuid.UUID, start: date, end: date) -> dict:
    """Pull the channel's subscriber count and per-video stats for the range into the creator tables."""
    token = await oauth.access_token(integ, oauth.GOOGLE)
    ctx = CallContext(session, "youtube", "youtube.sync", org_id=integ.org_id, workspace_id=integ.workspace_id,
                      integration_id=integ.id)
    ident = await youtube_identity(session, token, integ.org_id, integ.workspace_id)
    if ident["id"] != integ.external_account_id:
        raise IntegrationError("account_changed", "The connected Google account now points to a different channel. "
                               "Reconnect it.")
    today = datetime.now(UTC).date()
    snapshots = 0
    if ident["subscribers"] is not None:
        snap = (await session.execute(select(FollowerSnapshot).where(
            FollowerSnapshot.workspace_id == integ.workspace_id, FollowerSnapshot.platform == "youtube",
            FollowerSnapshot.captured_on == today))).scalar_one_or_none()
        if snap is None:
            session.add(FollowerSnapshot(workspace_id=integ.workspace_id, org_id=integ.org_id, platform="youtube",
                                         captured_on=today, followers=ident["subscribers"], source="integration",
                                         created_by=user_id))
        elif snap.source == "integration":
            snap.followers = ident["subscribers"]
        snapshots = 1
    report = json_of(await request(ctx, YT_LIMITS, "GET", "https://youtubeanalytics.googleapis.com/v2/reports",
                                   headers={"Authorization": f"Bearer {token}"},
                                   params={"ids": "channel==MINE", "startDate": start.isoformat(),
                                           "endDate": end.isoformat(), "dimensions": "video",
                                           "metrics": "views,likes,comments,shares", "sort": "-views",
                                           "maxResults": "50"}))
    cols = [c["name"] for c in report.get("columnHeaders", [])]
    rows = [dict(zip(cols, r, strict=False)) for r in report.get("rows", [])]
    titles: dict[str, dict] = {}
    ids = [r["video"] for r in rows if r.get("video")]
    for i in range(0, len(ids), 50):
        vids = json_of(await request(ctx, YT_LIMITS, "GET", "https://www.googleapis.com/youtube/v3/videos",
                                     headers={"Authorization": f"Bearer {token}"},
                                     params={"part": "snippet", "id": ",".join(ids[i:i + 50])}))
        for v in vids.get("items", []):
            titles[v["id"]] = {"title": v["snippet"]["title"][:200],
                               "published": v["snippet"]["publishedAt"][:10]}
    written = 0
    for r in rows:
        vid = r.get("video")
        if not vid:
            continue
        meta = titles.get(vid, {"title": f"Video {vid}", "published": start.isoformat()})
        url = f"https://www.youtube.com/watch?v={vid}"
        existing = (await session.execute(select(PostMetric).where(
            PostMetric.workspace_id == integ.workspace_id, PostMetric.platform == "youtube", PostMetric.post_url == url,
            PostMetric.captured_on == today, PostMetric.source == "integration"))).scalar_one_or_none()
        vals = {"video_views": _int(r.get("views")), "likes": _int(r.get("likes")), "comments": _int(r.get("comments")),
                "shares": _int(r.get("shares"))}
        if existing:
            for k, v in vals.items():
                setattr(existing, k, v)
        else:
            session.add(PostMetric(workspace_id=integ.workspace_id, org_id=integ.org_id, platform="youtube",
                                   post_url=url, post_label=meta["title"],
                                   published_on=date.fromisoformat(meta["published"]), captured_on=today,
                                   source="integration", created_by=user_id,
                                   notes=f"YouTube Analytics {start.isoformat()} to {end.isoformat()}", **vals))
        written += 1
    await session.flush()
    await oauth.mark(integ.id, synced=True)
    return {"channel": ident["title"], "subscribers": ident["subscribers"], "videos": written,
            "snapshots": snapshots, "range": [start.isoformat(), end.isoformat()]}


def _int(v) -> int | None:
    try:
        return max(0, int(Decimal(str(v))))
    except (InvalidOperation, ValueError, TypeError):
        return None
