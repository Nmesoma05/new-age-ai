async def test_signup_creates_user_personal_org_and_product(client, signup):
    a = await signup("Ada", product="creator")
    me = await client.get("/v1/me", headers=a.h)
    assert me.status_code == 200 and me.json()["display_name"] == "Ada"
    orgs = (await client.get("/v1/orgs", headers=a.h)).json()
    assert [(o["kind"], o["role"]) for o in orgs] == [("personal", "owner")]
    products = (await client.get(f"/v1/orgs/{a.org_id}/products", headers=a.h)).json()
    assert [p["product"] for p in products] == ["creator"]


async def test_password_is_hashed_never_returned(client, signup, owner_db):
    a = await signup()
    body = (await client.get("/v1/me", headers=a.h)).json()
    assert "password_hash" not in body and "password" not in body
    h = owner_db.execute("SELECT password_hash FROM users WHERE id = %s", (a.user_id,)).fetchone()[0]
    assert h.startswith("$argon2id$") and "correct-horse" not in h


async def test_duplicate_email_rejected(client, signup):
    a = await signup()
    r = await client.post("/v1/auth/signup", json={"email": a.email, "password": "another-password1",
                                                    "display_name": "X"})
    assert r.status_code == 409 and r.json()["code"] == "email_in_use"


async def test_validation_errors_are_problem_json(client):
    r = await client.post("/v1/auth/signup", json={"email": "not-an-email", "password": "short", "display_name": ""})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "validation_failed" and body["request_id"]
    assert {tuple(e["loc"])[-1] for e in body["errors"]} >= {"email", "password", "display_name"}


async def test_login_wrong_password_and_lockout(client, signup, owner_db):
    a = await signup()
    for _ in range(10):
        r = await client.post("/v1/auth/login", json={"email": a.email, "password": "wrong-password"})
        assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"
    r = await client.post("/v1/auth/login", json={"email": a.email, "password": "correct-horse-battery"})
    assert r.status_code == 429 and r.json()["code"] == "account_locked"
    n = owner_db.execute("SELECT count(*) FROM audit_events WHERE action = 'auth.login_failed'").fetchone()[0]
    assert n == 10


async def test_unknown_email_same_error_as_wrong_password(client):
    r = await client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever-123"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_credentials"


async def test_refresh_rotation_and_reuse_detection(client, signup):
    a = await signup()
    r1 = await client.post("/v1/auth/refresh", json={"refresh_token": a.refresh})
    assert r1.status_code == 200
    new_refresh = r1.json()["refresh_token"]
    # reusing the old (rotated) token revokes the whole family
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": a.refresh})
    assert r2.status_code == 401
    r3 = await client.post("/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r3.status_code == 401


async def test_logout_revokes_refresh_token(client, signup):
    a = await signup()
    assert (await client.post("/v1/auth/logout", json={"refresh_token": a.refresh})).status_code == 204
    assert (await client.post("/v1/auth/refresh", json={"refresh_token": a.refresh})).status_code == 401


async def test_missing_or_bad_token(client):
    assert (await client.get("/v1/me")).status_code == 401
    r = await client.get("/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_token"


async def test_token_signed_with_other_secret_rejected(client, signup):
    import jwt
    a = await signup()
    forged = jwt.encode({"sub": str(a.user_id), "iss": "ecosystem-api", "typ": "access", "iat": 1, "exp": 4102444800},
                        "a-completely-different-secret-value-xxxxxxxx", algorithm="HS256")
    assert (await client.get("/v1/me", headers={"Authorization": f"Bearer {forged}"})).status_code == 401


async def test_update_me(client, signup):
    a = await signup()
    r = await client.patch("/v1/me", headers=a.h, json={"display_name": "Ada O.", "country": "GH"})
    assert r.status_code == 200 and r.json()["display_name"] == "Ada O." and r.json()["country"] == "GH"
