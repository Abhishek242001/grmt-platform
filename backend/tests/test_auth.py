def _signup(client, email="researcher@example.com", password="Password1", role="researcher"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "full_name": "Test User", "role": role},
    )


def test_signup_creates_user_and_returns_tokens(client):
    resp = _signup(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "researcher@example.com"
    assert body["user"]["role"] == "researcher"
    assert body["access_token"]
    assert body["refresh_token"]


def test_signup_duplicate_email_rejected(client):
    _signup(client)
    resp = _signup(client)
    assert resp.status_code == 409


def test_signup_cannot_self_assign_platform_admin(client):
    resp = _signup(client, role="platform_admin")
    assert resp.status_code == 422


def test_signup_weak_password_rejected(client):
    resp = _signup(client, password="allletters")
    assert resp.status_code == 422


def test_login_with_correct_credentials(client):
    _signup(client)
    resp = client.post("/api/auth/login", json={"email": "researcher@example.com", "password": "Password1"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password_rejected(client):
    _signup(client)
    resp = client.post("/api/auth/login", json={"email": "researcher@example.com", "password": "WrongPass1"})
    assert resp.status_code == 401


def test_login_nonexistent_email_same_error_as_wrong_password(client):
    resp = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "Password1"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_me_requires_valid_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401

    signup_resp = _signup(client)
    token = signup_resp.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "researcher@example.com"


def test_refresh_token_issues_new_access_token(client):
    signup_resp = _signup(client)
    refresh_token = signup_resp.json()["refresh_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token_used_as_refresh(client):
    signup_resp = _signup(client)
    access_token = signup_resp.json()["access_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401
