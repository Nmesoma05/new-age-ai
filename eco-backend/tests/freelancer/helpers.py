"""A realistic beginner profile used across freelancer tests (Nigeria-based UI designer)."""
PROFILE = {
    "full_name": "Chiamaka Obi", "headline": "UI/UX designer", "career_stage": "beginner",
    "summary": "Designer who likes fintech and simple, clear interfaces.",
    "country": "NG", "city": "Awka", "timezone": "Africa/Lagos", "currency": "NGN",
    "work_modes": ["freelance", "remote_full_time"], "interests": ["fintech"],
    "experiences": [{"title": "UI Designer (intern)", "organisation": "Kola Studio", "employment_type": "internship",
                     "period": "Jan 2025 - Jun 2025",
                     "achievements": ["Redesigned the onboarding screens for a savings app"]}],
    "education": [{"qualification": "B.Eng. Computer Engineering", "institution": "UNIZIK", "period": "2019-2024"}],
    "skills": [{"name": "Figma", "level": "intermediate"}, {"name": "User research", "level": "beginner"},
               {"name": "Webflow"}],
    "portfolio": [{"title": "Savings app onboarding redesign", "url": "https://example.com/case", "role": "UI designer",
                   "outcome": "Cut onboarding from 7 screens to 4"}],
    "certifications": [{"name": "Google UX Design Certificate", "issuer": "Google", "year": "2024"}],
    "languages": [{"language": "English", "level": "fluent"}, {"language": "Igbo", "level": "native"}],
    "payment_methods": ["Payoneer", "Local bank"],
    "availability": {"hours_per_week": 30},
    "targets": {"roles": ["Product designer"], "income_goal_monthly": 600, "currency": "USD"},
}


async def fl_ws(client, signup, make_workspace, name="Chiamaka", **over):
    a = await signup(name, product="freelancer")
    ws = await make_workspace(a, "My career", product="freelancer")
    r = await client.put(f"/v1/workspaces/{ws}/professional-profile", headers=a.h, json={**PROFILE, **over})
    assert r.status_code == 200, r.text
    return a, ws
