"""Creator & Marketing division logic that isn't HTTP: capability matrix, studio prompt building, performance
maths, CSV import/export and report rendering.

Rule for this module: numbers only ever come from rows people recorded. Nothing here fetches or estimates
platform data.
"""
from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from app.models import FollowerSnapshot, PostMetric

PLATFORMS = ("instagram", "x", "linkedin", "tiktok", "facebook", "youtube", "threads", "whatsapp", "pinterest", "other")
METRIC_FIELDS = ("impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "video_views")
ENGAGEMENT_FIELDS = ("likes", "comments", "shares", "saves")

# ---------------------------------------------------------------- what works today vs. what needs integrations
Status = Literal["operational", "manual", "requires_integration"]

CAPABILITIES: list[dict] = [
    {"feature": "AI assistant chat", "status": "operational",
     "detail": "Answers questions using this client's profile, memory and documents."},
    {"feature": "Content & copywriting studio", "status": "operational",
     "detail": "Drafts posts, threads, captions and scripts; every draft is editable and saved with version history."},
    {"feature": "Brand voice & strategy profiles", "status": "operational",
     "detail": "Per-client voice, audience personas and content pillars; AI can propose and you choose what to apply."},
    {"feature": "Content calendar & social strategy", "status": "operational",
     "detail": "Plan, schedule and track posts per client; AI can draft a dated plan you import."},
    {"feature": "Campaign planning", "status": "operational",
     "detail": "Campaigns with phases, channels, deliverables and KPIs, linked to calendar items."},
    {"feature": "Approval workflow", "status": "operational",
     "detail": "Submit, comment, request changes and approve inside the team, or share a review link with the client."},
    {"feature": "Exports", "status": "operational",
     "detail": "Content library (CSV, Markdown), calendar (CSV, iCalendar) and reports (CSV, Markdown, HTML)."},
    {"feature": "Audience & competitor research", "status": "manual",
     "detail": "Analyses the audience and competitor notes you enter and documents you upload. Live web research "
               "needs a research provider, which isn't connected."},
    {"feature": "Performance reporting", "status": "manual",
     "detail": "Reports are calculated from numbers you enter or upload as CSV from each platform's insights page."},
    {"feature": "Publishing / scheduling to platforms", "status": "requires_integration",
     "detail": "Nothing is posted automatically. Copy the approved content, post it yourself, then mark the calendar "
               "item as published with its link."},
    {"feature": "Automatic analytics import", "status": "partial",
     "detail": "YouTube only: an organisation admin can connect a channel (read-only) in Settings, then Sync pulls "
               "views, likes, comments, shares and subscribers. Every other platform: manual entry or CSV upload."},
    {"feature": "Inbox / comment replies", "status": "requires_integration",
     "detail": "Not available: reading or replying to platform comments and DMs needs platform integrations."},
]

PLATFORM_INTEGRATIONS = [
    {"platform": p, "publishing": "requires_integration",
     "analytics": "connect" if p == "youtube" else "requires_integration",
     "manual_tracking": "operational"} for p in PLATFORMS if p != "other"]


# ---------------------------------------------------------------- studio prompt building
def studio_message(kind: str, brief: str, *, platforms: list[str] | None = None, formats: list[str] | None = None,
                   count: int | None = None, start: date | None = None, end: date | None = None,
                   extra: str = "") -> str:
    """Builds the user message for a studio run. Structured lines (Date range, Platforms) are parsed back by the
    agents' validators, so the model is held to exactly what the user asked for."""
    lines = [brief.strip()]
    if platforms:
        lines.append("Platforms: " + ", ".join(platforms))
    if formats:
        lines.append("Formats: " + ", ".join(formats))
    if count:
        lines.append(f"Number of drafts: {count}")
    if start and end:
        lines.append(f"Date range: {start.isoformat()} to {end.isoformat()}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


# ---------------------------------------------------------------- performance maths
@dataclass
class PlatformTotals:
    platform: str
    posts: int = 0
    impressions: int = 0
    reach: int = 0
    engagements: int = 0
    clicks: int = 0
    video_views: int = 0
    missing: set = field(default_factory=lambda: {"impressions", "reach", "clicks", "video_views"})

    @property
    def engagement_rate(self) -> float | None:
        return round(100 * self.engagements / self.impressions, 2) if self.impressions else None


@dataclass
class ReportSummary:
    start: date
    end: date
    posts: int
    totals: PlatformTotals
    by_platform: list[PlatformTotals]
    top_posts: list[dict]
    followers: list[dict]
    sources: dict[str, int]
    posts_marked_published: int
    caveats: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        def pt(t: PlatformTotals) -> dict:
            d = {**t.__dict__, "engagement_rate": t.engagement_rate}
            d.pop("missing", None)
            for f in t.missing:  # nobody recorded this figure: show "not recorded", never a fake zero
                d[f] = None
            return d
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "posts": self.posts,
                "totals": pt(self.totals), "by_platform": [pt(t) for t in self.by_platform],
                "top_posts": self.top_posts, "followers": self.followers, "sources": self.sources,
                "posts_marked_published": self.posts_marked_published, "caveats": self.caveats}


def _eng(m: PostMetric) -> int:
    return sum(getattr(m, f) or 0 for f in ENGAGEMENT_FIELDS)


def summarise(start: date, end: date, metrics: list[PostMetric], followers: list[FollowerSnapshot],
              posts_marked_published: int) -> ReportSummary:
    totals = PlatformTotals("all")
    per: dict[str, PlatformTotals] = {}
    sources: dict[str, int] = {}
    for m in metrics:
        sources[m.source] = sources.get(m.source, 0) + 1
        for t in (totals, per.setdefault(m.platform, PlatformTotals(m.platform))):
            t.posts += 1
            t.missing -= {f for f in ("impressions", "reach", "clicks", "video_views") if getattr(m, f) is not None}
            t.impressions += m.impressions or 0
            t.reach += m.reach or 0
            t.engagements += _eng(m)
            t.clicks += m.clicks or 0
            t.video_views += m.video_views or 0
    top = sorted(metrics, key=lambda m: (_eng(m), m.impressions or 0), reverse=True)[:5]
    top_posts = [{"label": m.post_label, "platform": m.platform, "published_on": m.published_on.isoformat(),
                  "url": m.post_url, "impressions": m.impressions, "engagements": _eng(m)} for m in top]
    fol: dict[str, list[FollowerSnapshot]] = {}
    for f in sorted(followers, key=lambda f: f.captured_on):
        fol.setdefault(f.platform, []).append(f)
    follower_rows = [{"platform": p, "first": rows[0].followers, "first_on": rows[0].captured_on.isoformat(),
                      "last": rows[-1].followers, "last_on": rows[-1].captured_on.isoformat(),
                      "change": rows[-1].followers - rows[0].followers} for p, rows in fol.items()]
    caveats = []
    if not metrics:
        caveats.append("No performance figures were recorded for this period.")
    if sources.get("manual") or sources.get("csv_import"):
        caveats.append("Figures were entered by your team (by hand or CSV upload) and haven't been verified "
                       "against the platforms.")
    missing = sorted({f for m in metrics for f in METRIC_FIELDS if getattr(m, f) is None})
    if missing:
        caveats.append("Some posts are missing: " + ", ".join(missing) + ". Totals only count what was entered.")
    if metrics and len(metrics) < 5:
        caveats.append("Fewer than 5 posts have figures, so patterns may not hold.")
    return ReportSummary(start, end, len(metrics), totals, sorted(per.values(), key=lambda t: -t.impressions),
                         top_posts, follower_rows, sources, posts_marked_published, caveats)


def _n(v) -> str:
    return f"{v:,}" if isinstance(v, int) else ("n/a" if v is None else str(v))


def summary_text(s: ReportSummary) -> str:
    """What the report writer agent is given. It may only use these figures."""
    t = s.totals
    lines = [f"Performance summary for {s.start} to {s.end} (calculated by the system from data the team recorded; "
             f"sources: {', '.join(f'{k}={v}' for k, v in s.sources.items()) or 'none'}):",
             f"Posts with figures: {s.posts}", f"Posts marked published in the calendar: {s.posts_marked_published}",
             f"Impressions: {_n(None if 'impressions' in t.missing else t.impressions)}",
             f"Reach: {_n(None if 'reach' in t.missing else t.reach)}", f"Engagements (likes+comments+shares+saves): "
             f"{_n(t.engagements)}", f"Engagement rate: {t.engagement_rate if t.engagement_rate is not None else 'n/a'}%",
             f"Clicks: {_n(None if 'clicks' in t.missing else t.clicks)}",
             f"Video views: {_n(None if 'video_views' in t.missing else t.video_views)}"]
    for p in s.by_platform:
        lines.append(f"- {p.platform}: {p.posts} posts, {_n(p.impressions)} impressions, {_n(p.engagements)} "
                     f"engagements, rate {p.engagement_rate if p.engagement_rate is not None else 'n/a'}%")
    for tp in s.top_posts:
        lines.append(f"Top post: '{tp['label']}' on {tp['platform']} ({tp['published_on']}): "
                     f"{_n(tp['impressions'])} impressions, {_n(tp['engagements'])} engagements")
    for f in s.followers:
        lines.append(f"Followers on {f['platform']}: {_n(f['first'])} on {f['first_on']} to {_n(f['last'])} on "
                     f"{f['last_on']} (change {f['change']:+,})")
    lines += [f"Caveat: {c}" for c in s.caveats]
    return "\n".join(lines)


# ---------------------------------------------------------------- CSV import
CSV_ALIASES = {"title": "post_label", "post": "post_label", "label": "post_label", "date": "published_on",
               "published": "published_on", "url": "post_url", "link": "post_url", "views": "video_views",
               "engagement_clicks": "clicks", "link_clicks": "clicks"}
MAX_CSV_ROWS = 2000


@dataclass
class CsvRow:
    platform: str
    post_label: str
    published_on: date
    post_url: str | None
    values: dict[str, int | None]


def parse_metrics_csv(data: bytes, default_platform: str | None = None) -> tuple[list[CsvRow], list[dict]]:
    """Returns (rows, errors). Each error is {row, message}; row numbers count the header as row 1."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], [{"row": 0, "message": "The file isn't UTF-8 text. Export it as CSV (UTF-8) and try again."}]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], [{"row": 0, "message": "The file has no header row."}]
    norm = {h: CSV_ALIASES.get(re.sub(r"[^a-z_]", "", h.strip().lower().replace(" ", "_")),
                               re.sub(r"[^a-z_]", "", h.strip().lower().replace(" ", "_"))) for h in reader.fieldnames}
    missing = [c for c in ("post_label", "published_on") if c not in norm.values()]
    if "platform" not in norm.values() and not default_platform:
        missing.append("platform")
    if missing:
        return [], [{"row": 1, "message": "Missing column(s): " + ", ".join(missing)}]
    rows, errors = [], []
    for i, raw in enumerate(reader, start=2):
        if i - 1 > MAX_CSV_ROWS:
            errors.append({"row": i, "message": f"Too many rows; the limit is {MAX_CSV_ROWS}."})
            break
        r = {norm[k]: (v or "").strip() for k, v in raw.items() if k in norm}
        if not any(r.values()):
            continue
        platform = (r.get("platform") or default_platform or "").lower()
        if platform == "twitter":
            platform = "x"
        if platform not in PLATFORMS:
            errors.append({"row": i, "message": f"Unknown platform {platform!r}."})
            continue
        try:
            published = date.fromisoformat(r.get("published_on", "")[:10])
        except ValueError:
            errors.append({"row": i, "message": "published_on must be a date like 2026-11-30."})
            continue
        label = r.get("post_label", "")[:200]
        if not label:
            errors.append({"row": i, "message": "post_label (title) is empty."})
            continue
        url = r.get("post_url") or None
        if url and not re.match(r"^https?://\S+$", url):
            errors.append({"row": i, "message": "post_url must start with http:// or https://."})
            continue
        values, bad = {}, None
        for f in METRIC_FIELDS:
            v = r.get(f, "").replace(",", "")
            if v == "":
                values[f] = None
            elif v.isdigit():
                values[f] = int(v)
            else:
                bad = f
                break
        if bad:
            errors.append({"row": i, "message": f"{bad} must be a whole number (or left empty)."})
            continue
        rows.append(CsvRow(platform, label, published, url, values))
    return rows, errors


# ---------------------------------------------------------------- exports
def csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        # neutralise spreadsheet formula injection in user/AI-provided cells
        w.writerow([("'" + c) if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r") else c for c in r])
    return buf.getvalue().encode("utf-8")


def ics_bytes(items: list, calendar_name: str) -> bytes:
    def esc(s: str) -> str:
        s = s.replace("\r\n", "\n").replace("\r", "\n")  # a bare CR would end the line in some parsers
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//New Age Media//New Age AI Creator calendar//EN",
           f"X-WR-CALNAME:{esc(calendar_name)}"]
    for it in items:
        dt = it.scheduled_for.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        out += ["BEGIN:VEVENT", f"UID:{it.id}@ecosystem", f"DTSTAMP:{now}", f"DTSTART:{dt}",
                f"SUMMARY:{esc(f'[{it.platform}] {it.title}')}",
                f"DESCRIPTION:{esc(f'Status: {it.status}. {it.notes}'.strip())}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return ("\r\n".join(out) + "\r\n").encode("utf-8")


def report_markdown(client: str, s: ReportSummary, narrative: str | None) -> str:
    t = s.totals
    out = [f"# Performance report: {client}", f"{s.start} to {s.end}", "",
           "> Figures were recorded by your team (manual entry or CSV upload). They were not fetched from the "
           "platforms.", "", "## Totals", "| Posts | Impressions | Reach | Engagements | Engagement rate | Clicks | Video views |",
           "|---|---|---|---|---|---|---|",
           f"| {s.posts} | {_n(None if 'impressions' in t.missing else t.impressions)} | "
           f"{_n(None if 'reach' in t.missing else t.reach)} | {_n(t.engagements)} | "
           f"{'n/a' if t.engagement_rate is None else str(t.engagement_rate) + '%'} | "
           f"{_n(None if 'clicks' in t.missing else t.clicks)} | {_n(None if 'video_views' in t.missing else t.video_views)} |"]
    if s.by_platform:
        out += ["", "## By platform", "| Platform | Posts | Impressions | Engagements | Rate |", "|---|---|---|---|---|"]
        out += [f"| {p.platform} | {p.posts} | {_n(p.impressions)} | {_n(p.engagements)} | "
                f"{'n/a' if p.engagement_rate is None else str(p.engagement_rate) + '%'} |" for p in s.by_platform]
    if s.top_posts:
        out += ["", "## Top posts", "| Post | Platform | Date | Impressions | Engagements |", "|---|---|---|---|---|"]
        out += [f"| {tp['label']} | {tp['platform']} | {tp['published_on']} | {_n(tp['impressions'])} | "
                f"{_n(tp['engagements'])} |" for tp in s.top_posts]
    if s.followers:
        out += ["", "## Followers", "| Platform | Start | End | Change |", "|---|---|---|---|"]
        out += [f"| {f['platform']} | {_n(f['first'])} ({f['first_on']}) | {_n(f['last'])} ({f['last_on']}) | "
                f"{f['change']:+,} |" for f in s.followers]
    if narrative:
        out += ["", "## Commentary (AI-written from the figures above)", narrative]
    if s.caveats:
        out += ["", "## About this data", *(f"- {c}" for c in s.caveats)]
    return "\n".join(out) + "\n"


def markdown_to_html(md: str, title: str) -> str:
    """Small, safe Markdown subset → standalone HTML (everything is escaped first)."""
    body, in_table, in_list = [], False, False
    for line in md.splitlines():
        e = html.escape(line)
        e = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e)
        e = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>", e)
        if line.startswith("|"):
            cells = [c.strip() for c in e.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                body.append("<table>")
                in_table = True
                body.append("<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>")
            else:
                body.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            body.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{e[2:]}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if line.startswith("# "):
            body.append(f"<h1>{e[2:]}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{e[3:]}</h2>")
        elif line.startswith("### "):
            body.append(f"<h3>{e[4:]}</h3>")
        elif line.startswith("&gt; "):
            body.append(f"<p class='note'>{e[5:]}</p>")
        elif line.strip():
            body.append(f"<p>{e}</p>")
    if in_table:
        body.append("</table>")
    if in_list:
        body.append("</ul>")
    css = ("body{font:15px/1.5 'Instrument Sans',system-ui,sans-serif;background:#F4EBDD;color:#171717;max-width:900px;"
           "margin:32px auto;padding:0 16px}h1{font-family:'Bricolage Grotesque',system-ui;font-size:28px}"
           "table{border-collapse:collapse;width:100%;margin:8px 0 16px;background:#FBF6EE}"
           "th,td{border:1px solid #D7C9B4;padding:6px 8px;text-align:left;font-variant-numeric:tabular-nums}"
           "th{background:#EADFCC}.note{background:#F6E3BC;padding:8px 12px;border-radius:6px}"
           "@media print{body{background:#fff}}")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{css}</style>"
            f"</head><body>{''.join(body)}</body></html>")
