"""Every external integration the three divisions need, with its verified constraints.

`status` is the honest state in this codebase:
  implemented  - code, tests and UI exist; it works once its credentials (if any) are configured
  planned      - designed and documented; no code calls this provider yet
Capabilities and access rules were checked against official docs on VERIFIED_ON (see docs/INTEGRATIONS.md for
sources). They change: re-check before building or enabling each one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

VERIFIED_ON = "2026-11-12"
Access = Literal["read", "write", "spend"]
Status = Literal["implemented", "planned"]


@dataclass(frozen=True)
class Integration:
    key: str
    name: str
    vendor: str
    products: tuple[str, ...]
    category: str
    access: Access
    auth: Literal["oauth2", "api_key", "none"]
    status: Status
    priority: int                       # 1 = read-only/low risk first ... 4 = spends money
    docs_url: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    access_requirements: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    approval: str = "None: read-only."
    fallback: str = ""
    config: tuple[str, ...] = ()        # env vars needed to enable it
    connectable: bool = False           # per-workspace account connection (OAuth) vs app-wide service
    notes: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict:
        return asdict(self)


CATALOG: tuple[Integration, ...] = (
    # ------------------------------------------------------------------ priority 1: read-only, implemented
    Integration(
        key="fx_exchangerate_api", name="Exchange rates", vendor="ExchangeRate-API (open access)",
        products=("freelancer", "business"), category="currency", access="read", auth="none", status="implemented",
        priority=1, docs_url="https://www.exchangerate-api.com/docs/free",
        reads=("Daily reference rates for ~160 currencies incl. NGN, KES, GHS, ZAR, XOF, XAF",),
        limits=("Updated once a day; rate limited (HTTP 429 lifts after ~20 min); request at most hourly",
                "Attribution link required wherever rates are shown; caching allowed; no redistribution"),
        fallback="Amounts stay in their own currency, labelled 'not converted'.",
        notes=("Chosen over ECB-based APIs because ECB reference rates don't cover most African currencies.",
               "Indicative rates only: not what a bank or payment provider will pay out.")),
    Integration(
        key="remotive", name="Remotive remote jobs", vendor="Remotive", products=("freelancer",), category="jobs",
        access="read", auth="none", status="implemented", priority=1,
        docs_url="https://github.com/remotive-com/remote-jobs-api",
        reads=("Public remote job listings: title, company, category, required location, salary text, URL",),
        limits=("Fetch at most ~4 times a day (app-wide); >2 requests/minute are blocked",
                "Listings are delayed 24h; must link back to the Remotive URL and credit Remotive",
                "Don't submit jobs to other job sites; don't use jobs to collect sign-ups or emails"),
        fallback="Add listings by hand; the directory of job boards stays available.",
        notes=("Imported listings are saved as unverified opportunities with the Remotive link.",)),
    Integration(
        key="youtube", name="YouTube channel analytics", vendor="Google (YouTube Data API v3 + YouTube Analytics API)",
        products=("creator",), category="analytics", access="read", auth="oauth2", status="implemented", priority=1,
        docs_url="https://developers.google.com/youtube/analytics/v1/reports/query", connectable=True,
        reads=("Channel title and subscriber count", "Per-video views, likes, comments, shares for a date range"),
        scopes=("https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/yt-analytics.readonly"),
        access_requirements=("Google Cloud project with both APIs enabled and an OAuth web client",
                             "Sensitive-scope verification (privacy policy on your domain, domain verification, demo "
                             "video, brand verification) before public launch; until then only test users can connect"),
        limits=("Data API default 10,000 units/day per project; list reads cost ~1 unit",
                "Analytics reports only include days where all requested metrics are available"),
        fallback="Enter or CSV-import metrics as before (source: manual).",
        config=("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "PUBLIC_WEB_URL")),
    # ------------------------------------------------------------------ priority 2: read-only, planned
    Integration(
        key="instagram", name="Instagram insights", vendor="Meta (Instagram Platform)", products=("creator", "business"),
        category="analytics", access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://developers.facebook.com/docs/instagram-platform/app-review",
        reads=("Professional account profile and media", "Insights (Facebook Login configuration: instagram_manage_insights)"),
        scopes=("instagram_basic", "instagram_manage_insights", "pages_show_list", "pages_read_engagement"),
        access_requirements=("Professional (Business/Creator) accounts only",
                             "Advanced Access via App Review + Business Verification to serve accounts you don't manage",
                             "An app uses either Facebook Login or Instagram Login, not both"),
        limits=("Business Use Case limit: 4,800 x impressions per app-account pair per rolling 24h",
                "Long-lived tokens last 60 days and must be refreshed"),
        fallback="Manual/CSV metrics."),
    Integration(
        key="facebook_pages", name="Facebook Page insights", vendor="Meta (Pages API)", products=("creator", "business"),
        category="analytics", access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://developers.facebook.com/documentation/pages-api/platforminsights/page",
        reads=("Page-level and post-level insights",), scopes=("pages_read_engagement", "read_insights"),
        access_requirements=("The connecting person must be able to do the 'analyze' task on the Page",
                             "App Review for accounts you don't manage"),
        limits=("Several Page Insights metrics were deprecated for all API versions by June 15, 2026: use the "
                "current metric list",), fallback="Manual/CSV metrics."),
    Integration(
        key="linkedin_pages", name="LinkedIn Page analytics", vendor="LinkedIn (Community Management API)",
        products=("creator", "business"), category="analytics", access="read", auth="oauth2", status="planned",
        priority=2, connectable=True, docs_url="https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review",
        reads=("Organization page followers and post performance",),
        access_requirements=("Registered legal organisation, verified business email, website, privacy policy",
                             "Development tier, then Standard tier with a screencast; a rejected app can't reapply",
                             "A LinkedIn Page super admin must verify the app"),
        fallback="Manual/CSV metrics.", notes=("Scope names to confirm in the Developer Portal product page.",)),
    Integration(
        key="tiktok_display", name="TikTok profile & video stats", vendor="TikTok for Developers",
        products=("creator",), category="analytics", access="read", auth="oauth2", status="planned", priority=2,
        connectable=True, docs_url="https://developers.tiktok.com/doc/tiktok-api-scopes/",
        reads=("Follower/like counts (user.info.stats)", "The user's public videos (video.list)"),
        scopes=("user.info.basic", "user.info.stats", "video.list"),
        access_requirements=("App review of requested scopes",), fallback="Manual/CSV metrics."),
    Integration(
        key="x_api", name="X (Twitter) metrics", vendor="X Corp (X API v2)", products=("creator",),
        category="analytics", access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://docs.x.com/x-api/getting-started/pricing",
        reads=("Own posts and their public metrics",),
        access_requirements=("Pay-per-use credits; legacy Basic/Pro plans are deprecated",),
        limits=("Owned reads $0.001/resource; post reads $0.005; 3M post reads per billing cycle cap",
                "Every call costs money: needs a spending limit and per-workspace budget before enabling"),
        fallback="Manual/CSV metrics.",
        notes=("Even reads spend money here, so it's treated as a cost-bearing integration.",)),
    Integration(
        key="ga4", name="Google Analytics 4", vendor="Google (Analytics Data API)", products=("business",),
        category="analytics", access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://developers.google.com/analytics/devguides/reporting/data/v1/quotas",
        reads=("Sessions, conversions/key events, revenue by source/medium and date",),
        scopes=("https://www.googleapis.com/auth/analytics.readonly",),
        limits=("Core quota per standard property: 200,000 tokens/day, 40,000/hour, 10 concurrent requests",),
        access_requirements=("Google sensitive-scope verification",), fallback="Manual/CSV results."),
    Integration(
        key="google_business_profile", name="Google Business Profile performance",
        vendor="Google (Business Profile Performance API)", products=("business",), category="analytics",
        access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://developers.google.com/my-business/reference/performance/rest",
        reads=("Daily search/map impressions, website clicks, call clicks, direction requests",),
        scopes=("https://www.googleapis.com/auth/business.manage",),
        access_requirements=("Access request form; new projects start at 0 quota until Google approves",),
        fallback="Manual/CSV results."),
    Integration(
        key="hubspot", name="HubSpot CRM", vendor="HubSpot", products=("business",), category="crm", access="read",
        auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://developers.hubspot.com/docs/api-reference/latest/authentication/manage-oauth-tokens",
        reads=("Contacts/deals counts by source and stage, for lead and customer results",),
        scopes=("crm.objects.contacts.read", "crm.objects.deals.read"),
        limits=("Access tokens last 30 minutes; refresh with the refresh token",),
        fallback="Manual/CSV results.", notes=("Read-only first; writing CRM records is a later, approved action.",)),
    Integration(
        key="google_calendar", name="Google Calendar (interviews, follow-ups)", vendor="Google (Calendar API)",
        products=("freelancer", "creator"), category="calendar", access="write", auth="oauth2", status="planned",
        priority=3, connectable=True, docs_url="https://developers.google.com/calendar/api/auth",
        writes=("Create events only on calendars the user owns",),
        scopes=("https://www.googleapis.com/auth/calendar.events.owned",),
        approval="Each event is shown first and created only after the user approves it.",
        fallback="Download an .ics file (already available in Creator)."),
    Integration(
        key="brave_search", name="Live web research", vendor="Brave Search API", products=("creator", "business", "freelancer"),
        category="research", access="read", auth="api_key", status="planned", priority=2,
        docs_url="https://api-dashboard.search.brave.com/app/plans",
        reads=("Web results with URLs for the researcher agent to cite",),
        limits=("Metered: about $5 per 1,000 searches (Feb 2026 change); public attribution needed to keep "
                "monthly credits", "Check current terms on storing results before caching"),
        approval="None, but it costs money per search: needs a monthly budget cap.",
        fallback="Research uses only the user's documents and notes (as now)."),
    # ------------------------------------------------------------------ priority 3: writes (publish/send), planned
    Integration(
        key="instagram_publish", name="Instagram publishing", vendor="Meta (Instagram Platform)", products=("creator",),
        category="publishing", access="write", auth="oauth2", status="planned", priority=3, connectable=True,
        docs_url="https://developers.facebook.com/documentation/instagram-platform/overview",
        writes=("Publish images, videos, reels, carousels",),
        scopes=("instagram_business_content_publishing (Instagram Login) or instagram_content_publishing",),
        access_requirements=("App Review + Business Verification for Advanced Access",),
        approval="Explicit approval of the exact post, account and time; a client review link doesn't count.",
        fallback="Copy the post, publish manually, then 'Mark published'."),
    Integration(
        key="threads_publish", name="Threads publishing", vendor="Meta (Threads API)", products=("creator",),
        category="publishing", access="write", auth="oauth2", status="planned", priority=3, connectable=True,
        docs_url="https://developers.facebook.com/documentation/threads/overview",
        scopes=("threads_basic", "threads_content_publish"), limits=("250 API posts per profile per rolling 24h",),
        approval="Explicit approval per post.", fallback="Manual posting."),
    Integration(
        key="linkedin_publish", name="LinkedIn posting", vendor="LinkedIn", products=("creator", "business", "freelancer"),
        category="publishing", access="write", auth="oauth2", status="planned", priority=3, connectable=True,
        docs_url="https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review",
        access_requirements=("Community Management API Standard tier",),
        approval="Explicit approval per post.", fallback="Manual posting."),
    Integration(
        key="x_publish", name="X posting", vendor="X Corp", products=("creator", "freelancer"), category="publishing",
        access="spend", auth="oauth2", status="planned", priority=4, connectable=True,
        docs_url="https://docs.x.com/x-api/getting-started/pricing",
        limits=("$0.015 per post; $0.20 per post containing a URL",),
        approval="Explicit approval per post, showing the API cost.", fallback="Manual posting."),
    Integration(
        key="tiktok_publish", name="TikTok posting", vendor="TikTok (Content Posting API)", products=("creator",),
        category="publishing", access="write", auth="oauth2", status="planned", priority=3, connectable=True,
        docs_url="https://developers.tiktok.com/doc/content-posting-api-get-started", scopes=("video.publish", "video.upload"),
        access_requirements=("Until the app passes TikTok's audit, everything it posts is private-only",),
        approval="Explicit approval per post.", fallback="Upload as a draft (video.upload) or post manually."),
    Integration(
        key="youtube_upload", name="YouTube upload", vendor="Google (YouTube Data API)", products=("creator",),
        category="publishing", access="write", auth="oauth2", status="planned", priority=3, connectable=True,
        docs_url="https://developers.google.com/youtube/v3/getting-started",
        limits=("Default allocation includes 100 videos.insert calls/day per project",),
        access_requirements=("Quota/compliance audit for production use; verify current rules for unaudited "
                             "projects' upload visibility before enabling",),
        approval="Explicit approval per upload.", fallback="Manual upload."),
    Integration(
        key="whatsapp_cloud", name="WhatsApp Business messaging", vendor="Meta (WhatsApp Cloud API)",
        products=("business",), category="messaging", access="spend", auth="api_key", status="planned", priority=4,
        docs_url="https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing",
        writes=("Template messages to opted-in customers; free-form replies inside the 24h service window",),
        limits=("Charged per delivered template message since July 1, 2025 (marketing/utility/authentication)",
                "Service messages free inside the customer-service window"),
        access_requirements=("WhatsApp Business Account, verified number, approved templates",
                             "Recorded opt-in for every recipient"),
        approval="Explicit approval of template, audience (count) and estimated cost; workspace admin + org admin.",
        fallback="Export the message and audience to send from the WhatsApp Business app."),
    Integration(
        key="sms_ng", name="SMS (Nigeria-first)", vendor="Termii or Twilio", products=("business",),
        category="messaging", access="spend", auth="api_key", status="planned", priority=4,
        docs_url="https://www.twilio.com/en-us/guidelines/ng/sms",
        access_requirements=("Pre-registered alphanumeric sender ID (about 2-3 weeks); numeric senders fail on major "
                             "Nigerian networks", "Opt-in consent; NCC Do-Not-Disturb registry respected"),
        limits=("No two-way SMS in Nigeria via Twilio; promotional content can't use international sender IDs",),
        approval="Explicit approval with recipient count and cost estimate.", fallback="Export a CSV for the user's own SMS tool."),
    Integration(
        key="email_send", name="Email campaigns", vendor="An email service provider (e.g. Brevo, Mailchimp, Postmark)",
        products=("business", "freelancer"), category="messaging", access="write", auth="api_key", status="planned",
        priority=3, docs_url="", approval="Explicit approval with recipient count; only opted-in lists.",
        fallback="Copy the email; send from the user's own mail tool.",
        notes=("Provider not chosen yet: verify sending-domain authentication (SPF/DKIM/DMARC) and consent rules first.",)),
    # ------------------------------------------------------------------ priority 4: spend money, planned
    Integration(
        key="meta_ads", name="Meta ads", vendor="Meta (Marketing API)", products=("business",), category="ads",
        access="spend", auth="oauth2", status="planned", priority=4, connectable=True,
        docs_url="https://developers.facebook.com/docs/marketing-api/access/",
        reads=("Campaign spend, results (ads_read)",), writes=("Create campaigns PAUSED; activate only after approval",),
        scopes=("ads_read", "ads_management"),
        access_requirements=("Dev tier by default; Ads Management Standard Access needs App Review, a live app, "
                             "1,500+ calls in 30 days and <10% error rate",),
        approval="Read-only reporting needs none. Creating anything: approval. Activating/spending: workspace admin "
                 "+ org owner/admin, showing budget, dates and currency.",
        fallback="Plan in-app; launch in Ads Manager; record results."),
    Integration(
        key="google_ads", name="Google Ads", vendor="Google (Google Ads API)", products=("business",), category="ads",
        access="spend", auth="oauth2", status="planned", priority=4, connectable=True,
        docs_url="https://developers.google.com/google-ads/api/docs/api-policy/access-levels",
        reads=("Campaign metrics",), writes=("Campaigns created paused, enabled only after approval",),
        scopes=("https://www.googleapis.com/auth/adwords",),
        access_requirements=("Since Sept 9, 2026 access is per Google Cloud project (developer tokens sunset): "
                             "Explorer (2,880 prod ops/day), Basic (15,000; brand verification), Standard (audit)",),
        approval="As Meta ads.", fallback="Plan in-app; launch in Google Ads; record results."),
    Integration(
        key="paystack_billing", name="Subscription billing", vendor="Paystack", products=("creator", "business", "freelancer"),
        category="payments", access="spend", auth="api_key", status="planned", priority=4,
        docs_url="https://paystack.com/docs/payments/subscriptions/",
        writes=("Plans, subscriptions (card, Nigerian direct debit)",),
        limits=("Failed subscription charges aren't retried by Paystack",),
        approval="The customer authorises payment in Paystack's own checkout; we never handle card data.",
        fallback="Plans activated by an admin (as now).", notes=("Partly present: the inbound webhook receiver (HMAC-SHA512 signature check, raw event stored) exists "
               "from the backend phase. No outbound Paystack call (checkout, plans) is built; the signature scheme "
               "still needs confirming against Paystack's current docs.",)),
    Integration(
        key="upwork", name="Upwork", vendor="Upwork (GraphQL API)", products=("freelancer",), category="jobs",
        access="read", auth="oauth2", status="planned", priority=2, connectable=True,
        docs_url="https://www.upwork.com/developer/documentation/graphql",
        access_requirements=("API key request and approval by Upwork; terms not verified yet (docs page didn't load)",),
        fallback="Paste Upwork listings into Opportunities."),
)

BY_KEY = {i.key: i for i in CATALOG}


def for_product(product: str) -> list[dict]:
    return [i.as_dict() for i in sorted(CATALOG, key=lambda x: (x.priority, x.status != "implemented", x.name))
            if product in i.products]
