BIZ = {"business_name": "Mama Nkechi's Kitchen", "category": "food_hospitality", "industry": "Catering",
       "sub_type": "Party trays", "stage": "new", "business_model": "b2c", "location": "Awka, Nigeria",
       "target_markets": ["Awka", "Onitsha"], "offers": [{"name": "Small chops tray", "price": "NGN 25,000"},
                                                          {"name": "Jollof party pack", "price": "NGN 40,000"}],
       "customers": "Families and event planners hosting parties", "differentiators": "Same-day delivery, home recipes",
       "competitors": [{"name": "Chop Express", "notes": "Cheaper but often late"}],
       "channels": [{"channel": "whatsapp", "status": "using"}, {"channel": "instagram", "status": "tried"}],
       "goals": [{"goal": "More weekend party orders", "metric": "orders per weekend", "target": "20"}],
       "budget": {"monthly_amount": 50000, "currency": "NGN", "notes": "Can increase in December"}}


async def biz_ws(client, signup, make_workspace, **over):
    a = await signup("Ada", product="business")
    ws = await make_workspace(a, over.get("business_name", BIZ["business_name"]), product="business")
    r = await client.put(f"/v1/workspaces/{ws}/business-profile", headers=a.h, json={**BIZ, **over})
    assert r.status_code == 200, r.text
    return a, ws
