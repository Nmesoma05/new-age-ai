"""App-wide public data: exchange rates and the Remotive job feed (fetch caps, attribution, honest staleness)."""
import httpx

from tests.freelancer.conftest import fl  # noqa: F401


async def test_fx_convert_cached_with_attribution(client, signup, fake):
    a = await signup()
    r = await client.get("/v1/fx/convert?amount=100&from=USD&to=NGN", headers=a.h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["converted"] == 150050.0 and b["rate"] == 1500.5 and b["stale"] is False
    assert b["attribution"] == {"text": "Rates By Exchange Rate API", "url": "https://www.exchangerate-api.com"}
    assert "not what a bank" in b["note"]
    await client.get("/v1/fx/convert?amount=5&from=usd&to=KES", headers=a.h)
    assert fake.count("open.er-api.com") == 1  # one fetch per base per 12h, app-wide
    r = await client.get("/v1/fx/convert?amount=5&from=USD&to=XYZ", headers=a.h)
    assert r.status_code == 422 and r.json()["code"] == "unsupported_currency"
    r = await client.get("/v1/fx/convert?amount=5&from=US1&to=NGN", headers=a.h)
    assert r.status_code == 422


async def test_fx_outage_serves_dated_stale_rates_or_fails_honestly(client, signup, fake, owner_db):
    a = await signup()
    fake.overrides[("open.er-api.com", "/v6/latest/EUR")] = httpx.Response(503)
    r = await client.get("/v1/fx/convert?amount=1&from=EUR&to=NGN", headers=a.h)
    assert r.status_code == 502 and r.json()["code"] == "provider_error"  # no cache: no number invented
    await client.get("/v1/fx/convert?amount=1&from=USD&to=NGN", headers=a.h)
    with owner_db.cursor() as c:
        c.execute("UPDATE external_cache SET expires_at = now() - interval '1 hour'")
    fake.overrides[("open.er-api.com", "/v6/latest/USD")] = httpx.Response(429)
    r = await client.get("/v1/fx/convert?amount=1&from=USD&to=NGN", headers=a.h)
    assert r.status_code == 200 and r.json()["stale"] is True and r.json()["rates_updated"]


async def test_remotive_search_import_and_caps(client, fl, fake):  # noqa: F811
    a, ws = await fl()
    r = await client.get(f"/v1/workspaces/{ws}/jobs/remotive?q=designer", headers=a.h)
    assert r.status_code == 200, r.text
    b = r.json()
    assert [j["title"] for j in b["jobs"]] == ["Product Designer"]
    assert b["attribution"]["url"] == "https://remotive.com" and "24 hours" in b["attribution"]["terms"]
    assert "<" not in b["jobs"][0]["snippet"] and "x()" not in b["jobs"][0]["snippet"]
    all_jobs = (await client.get(f"/v1/workspaces/{ws}/jobs/remotive", headers=a.h)).json()["jobs"]
    assert {j["id"] for j in all_jobs} == {"101", "102"}  # the non-Remotive URL is dropped
    assert fake.count("remotive.com") == 1  # one shared snapshot, not one fetch per search

    r = await client.post(f"/v1/workspaces/{ws}/jobs/remotive/import", headers=a.h, json={"job_id": "101"})
    assert r.status_code == 201, r.text
    oid = r.json()["id"]
    assert r.json()["status"] == "unverified"
    o = (await client.get(f"/v1/workspaces/{ws}/freelancer/opportunities/{oid}", headers=a.h)).json()
    assert o["source"] == "integration" and o["source_name"] == "Remotive" and o["status"] == "unverified"
    assert o["url"].startswith("https://remotive.com/") and o["eligible_countries"] == ["EUROPE", "AFRICA"]
    assert o["checks"]["eligibility"]["status"] == "eligible"  # PROFILE country is in Africa
    assert "Salary as listed: $50k - $70k" in o["description"]
    dup = await client.post(f"/v1/workspaces/{ws}/jobs/remotive/import", headers=a.h, json={"job_id": "101"})
    assert dup.status_code == 409
    us = await client.post(f"/v1/workspaces/{ws}/jobs/remotive/import", headers=a.h, json={"job_id": "102"})
    o2 = (await client.get(f"/v1/workspaces/{ws}/freelancer/opportunities/{us.json()['id']}", headers=a.h)).json()
    assert o2["kind"] == "contract" and o2["checks"]["eligibility"]["status"] == "not_eligible"
    gone = await client.post(f"/v1/workspaces/{ws}/jobs/remotive/import", headers=a.h, json={"job_id": "999"})
    assert gone.status_code == 404 and gone.json()["code"] == "job_gone"


async def test_remotive_outage_without_cache(client, fl, fake):  # noqa: F811
    a, ws = await fl()
    fake.overrides[("remotive.com", "/api/remote-jobs")] = httpx.Response(503)
    r = await client.get(f"/v1/workspaces/{ws}/jobs/remotive", headers=a.h)
    assert r.status_code == 502 and r.json()["retryable"] is True


async def test_remotive_only_in_freelancer_workspaces(client, signup, make_workspace, fake):
    a = await signup()
    ws = await make_workspace(a, "Creator ws", "creator")
    assert (await client.get(f"/v1/workspaces/{ws}/jobs/remotive", headers=a.h)).status_code == 404


def test_location_mapping_never_guesses():
    from app.integrations.providers import location_to_codes as m
    assert m("Worldwide") == ("remote_global", ["WORLDWIDE"])
    assert m("USA Only") == ("remote_regional", ["US"])
    assert m("UK/Canada") == ("remote_regional", ["GB", "CA"])
    assert m("Nigeria, Kenya") == ("remote_regional", ["NG", "KE"])
    assert m("Somewhere nice") == ("unknown", [])
    assert m("") == ("unknown", [])


async def test_concurrent_cache_misses_fetch_once_and_never_500(client, signup, fl, fake):  # noqa: F811
    """QA BUG-01: two simultaneous conversions both missed the cache and the second INSERT failed with a 500."""
    import asyncio
    a = await signup()
    rs = await asyncio.gather(*[client.get(f"/v1/fx/convert?amount={n}&from=USD&to=NGN", headers=a.h) for n in (1, 2, 3)])
    assert [r.status_code for r in rs] == [200, 200, 200]
    assert fake.count("open.er-api.com") == 1
    b, ws = await fl()
    rs = await asyncio.gather(*[client.get(f"/v1/workspaces/{ws}/jobs/remotive?q={q}", headers=b.h) for q in ("a", "b")])
    assert [r.status_code for r in rs] == [200, 200] and fake.count("remotive.com") == 1
