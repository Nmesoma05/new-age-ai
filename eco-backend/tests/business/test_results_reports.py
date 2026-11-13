"""Business workflow 3: recorded results, CSV import, report maths, AI analysis and exports."""
CSV = (b"channel,period_start,period_end,spend,leads,customers,revenue\n"
       b"Facebook Ads,2026-11-01,2026-11-15,\"20,000\",40,8,\"200,000\"\n"
       b"whatsapp,2026-11-01,2026-11-30,,20,4,100000\n")


async def _seed(client, a, ws):
    r = await client.post(f"/v1/workspaces/{ws}/business/results/import", headers=a.h,
                          files={"file": ("r.csv", CSV, "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


async def test_manual_and_csv_results(client, biz):
    a, ws = await biz()
    r = await client.post(f"/v1/workspaces/{ws}/business/results", headers=a.h,
                          json={"channel": "instagram", "period_start": "2026-11-01", "period_end": "2026-11-07"})
    assert r.status_code == 422  # at least one figure
    r = await client.post(f"/v1/workspaces/{ws}/business/results", headers=a.h,
                          json={"channel": "instagram", "period_start": "2026-11-01", "period_end": "2026-11-07", "leads": 5})
    assert r.status_code == 201 and r.json()["currency"] == "NGN" and r.json()["source"] == "manual"
    assert (await _seed(client, a, ws))["imported"] == 2
    bad = b"channel,period_start,leads\nmyspace,2026-11-01,3\nwhatsapp,nope,1\n"
    r = await client.post(f"/v1/workspaces/{ws}/business/results/import", headers=a.h, files={"file": ("b.csv", bad, "text/csv")})
    assert r.status_code == 422 and len(r.json()["rows"]) == 2
    rows = (await client.get(f"/v1/workspaces/{ws}/business/results?start=2026-11-01&end=2026-11-30", headers=a.h)).json()
    assert len(rows) == 3 and {x["source"] for x in rows} == {"manual", "csv_import"}
    assert {x["channel"] for x in rows} == {"instagram", "meta_ads", "whatsapp"}


async def test_report_maths_and_currencies(client, biz):
    a, ws = await biz()
    await _seed(client, a, ws)
    await client.post(f"/v1/workspaces/{ws}/business/results", headers=a.h,
                      json={"channel": "email", "period_start": "2026-11-02", "period_end": "2026-11-02",
                            "currency": "USD", "spend": "50", "leads": 2})
    s = (await client.get(f"/v1/workspaces/{ws}/business/report?start=2026-11-01&end=2026-11-30", headers=a.h)).json()
    t = s["totals"]
    assert s["currency"] == "NGN" and s["rows"] == 2 and s["other_currencies"] == ["USD"]
    assert t["spend"] == 20000 and t["leads"] == 60 and t["customers"] == 12 and t["revenue"] == 300000
    assert t["cost_per_lead"] == 333.33 and t["return_on_spend"] == 15.0 and t["lead_to_customer_pct"] == 20.0
    meta = next(c for c in s["by_channel"] if c["channel"] == "meta_ads")
    wa = next(c for c in s["by_channel"] if c["channel"] == "whatsapp")
    assert meta["cost_per_lead"] == 500.0 and wa["spend"] is None and wa["cost_per_lead"] is None
    assert any("USD" in c for c in s["caveats"]) and any("entered by your team" in c for c in s["caveats"])


async def test_ai_analysis_is_grounded_and_exported(client, biz, bgen, provider):
    a, ws = await biz()
    await _seed(client, a, ws)
    r = await bgen(a, ws, tool="report", start_date="2026-11-01", end_date="2026-11-30")
    assert r.status_code == 201, r.text
    run = r.json()["run"]
    assert run["output"]["headline"] == "60 leads recorded"
    sent = provider.sent_to("business.performance_analyst")[0].messages[-1].content
    assert "Leads: 60" in sent and "Cost per lead: NGN 333.33" in sent
    # A model inventing a figure is caught and repaired
    from tests.ai.scripted import final
    bad = final({"headline": "Leads grew 45% to 60", "what_worked": [], "what_to_improve": [], "budget_shifts": [],
                 "next_actions": ["x"], "data_caveats": ["y"], "uncertainties": [], "warnings": []})
    provider.on("business.performance_analyst", bad)
    r = await bgen(a, ws, tool="report", start_date="2026-11-01", end_date="2026-11-30")
    assert r.json()["run"]["output"]["headline"] == "60 leads recorded"
    assert "45" in provider.sent_to("business.performance_analyst")[-1].messages[-1].content
    base = f"/v1/workspaces/{ws}/business/report/export?start=2026-11-01&end=2026-11-30"
    md = (await client.get(base + f"&format=md&run_id={run['id']}", headers=a.h)).text
    assert "## Analysis (AI-written from the figures above)" in md and "not fetched from ad accounts" in md
    csv_ = (await client.get(base + "&format=csv", headers=a.h)).text
    assert csv_.splitlines()[0].startswith("channel,period_start") and "csv_import" in csv_
    html = await client.get(base + "&format=html", headers=a.h)
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")


async def test_campaign_results(client, biz):
    a, ws = await biz()
    c = (await client.post(f"/v1/workspaces/{ws}/business/campaigns", headers=a.h,
                           json={"name": "December parties", "channels": ["meta_ads", "whatsapp"],
                                 "start_date": "2026-12-01", "end_date": "2026-12-24"})).json()
    await client.post(f"/v1/workspaces/{ws}/business/results", headers=a.h,
                      json={"channel": "meta_ads", "campaign_id": c["id"], "period_start": "2026-12-01",
                            "period_end": "2026-12-07", "spend": "10000", "leads": 25})
    d = (await client.get(f"/v1/workspaces/{ws}/business/campaigns/{c['id']}", headers=a.h)).json()
    assert d["summary"]["totals"]["cost_per_lead"] == 400.0 and len(d["results"]) == 1
    r = await client.patch(f"/v1/workspaces/{ws}/business/campaigns/{c['id']}", headers=a.h, json={"status": "active"})
    assert r.json()["status"] == "active"
    assert (await client.post(f"/v1/workspaces/{ws}/business/campaigns", headers=a.h,
                              json={"name": "x", "channels": ["myspace"]})).status_code == 422
