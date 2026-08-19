from tests.conftest import auth_headers, signup_and_login


def test_signup_creates_user(client):
    resp = client.post(
        "/api/auth/signup",
        json={"email": "a@example.com", "password": "testpass123", "role": "researcher", "name": "Ada"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "a@example.com"
    assert body["role"] == "researcher"
    assert body["email_verified"] is False


def test_signup_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "testpass123", "role": "researcher", "name": "A"})
    resp = client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "testpass123", "role": "researcher", "name": "B"})
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "EMAIL_TAKEN"


def test_signup_rejects_invalid_role(client):
    # Reviewer/platform_admin are invite-only per master doc §1.2/§1.10 — no self-serve signup path.
    resp = client.post(
        "/api/auth/signup",
        json={"email": "sneaky@example.com", "password": "testpass123", "role": "platform_admin", "name": "X"},
    )
    assert resp.status_code == 422


def test_login_succeeds_with_correct_credentials(client):
    client.post("/api/auth/signup", json={"email": "login@example.com", "password": "testpass123", "role": "researcher", "name": "A"})
    resp = client.post("/api/auth/login", json={"email": "login@example.com", "password": "testpass123"})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body and "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_fails_with_wrong_password(client):
    client.post("/api/auth/signup", json={"email": "wrongpw@example.com", "password": "testpass123", "role": "researcher", "name": "A"})
    resp = client.post("/api/auth/login", json={"email": "wrongpw@example.com", "password": "WRONG"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_does_not_reveal_whether_email_exists(client):
    """master doc §6.3 — generic message, do not confirm whether the account exists."""
    resp = client.post("/api/auth/login", json={"email": "nonexistent@example.com", "password": "whatever"})
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "INVALID_CREDENTIALS"


def test_refresh_token_issues_new_access_token(client):
    client.post("/api/auth/signup", json={"email": "refresh@example.com", "password": "testpass123", "role": "researcher", "name": "A"})
    login_resp = client.post("/api/auth/login", json={"email": "refresh@example.com", "password": "testpass123"})
    refresh_token = login_resp.json()["refresh_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_rejects_access_token_used_as_refresh(client):
    client.post("/api/auth/signup", json={"email": "wrongtype@example.com", "password": "testpass123", "role": "researcher", "name": "A"})
    login_resp = client.post("/api/auth/login", json={"email": "wrongtype@example.com", "password": "testpass123"})
    access_token = login_resp.json()["access_token"]
    resp = client.post("/api/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


def test_protected_endpoint_rejects_missing_token(client):
    resp = client.get("/api/conferences")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_garbage_token(client):
    resp = client.get("/api/conferences", headers=auth_headers("not-a-real-jwt"))
    assert resp.status_code == 401


def test_protected_endpoint_accepts_valid_token(client):
    token = signup_and_login(client, email="valid@example.com")
    resp = client.get("/api/conferences", headers=auth_headers(token))
    assert resp.status_code == 200
