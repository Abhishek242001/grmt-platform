from tests.conftest import auth_headers, signup_and_login


def _make_platform_admin(client, db_session, email="admin@example.com"):
    """
    platform_admin is invite-only (development_rule.md §7) — no signup endpoint
    accepts it (see test_signup_rejects_invalid_role in test_auth.py), so
    tests create one directly against the DB, the way a seed script would.
    """
    from app.core.security import hash_password
    from app.models.core import User

    user = User(email=email, password_hash=hash_password("adminpass123"), role="platform_admin", name="Admin")
    db_session.add(user)
    db_session.commit()

    token_resp = client.post("/api/auth/login", json={"email": email, "password": "adminpass123"})
    return token_resp.json()["access_token"]


def test_non_admin_cannot_access_model_usage(client):
    token = signup_and_login(client, email="researcher_admin@example.com", role="researcher")
    resp = client.get("/api/admin/models/usage", headers=auth_headers(token))
    assert resp.status_code == 403


def test_platform_admin_can_access_model_usage(client, db_session):
    admin_token = _make_platform_admin(client, db_session)
    resp = client.get("/api/admin/models/usage", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    assert "services" in resp.json()
    assert "per_check_type" in resp.json()


def test_maintenance_mode_start_and_end(client, db_session):
    admin_token = _make_platform_admin(client, db_session, email="admin2@example.com")

    status_before = client.get("/api/admin/maintenance/status")
    assert status_before.json()["maintenance_mode"] is False

    start_resp = client.post("/api/admin/maintenance/start", headers=auth_headers(admin_token))
    assert start_resp.status_code == 200
    assert start_resp.json()["maintenance_mode"] is True

    status_during = client.get("/api/admin/maintenance/status")
    assert status_during.json()["maintenance_mode"] is True

    end_resp = client.post("/api/admin/maintenance/end", headers=auth_headers(admin_token))
    assert end_resp.json()["maintenance_mode"] is False


def test_non_admin_cannot_start_maintenance(client):
    token = signup_and_login(client, email="researcher_maint@example.com", role="researcher")
    resp = client.post("/api/admin/maintenance/start", headers=auth_headers(token))
    assert resp.status_code == 403


def test_false_positive_rate_endpoint_returns_empty_with_no_feedback_yet(client, db_session):
    admin_token = _make_platform_admin(client, db_session, email="admin3@example.com")
    resp = client.get("/api/admin/models/false-positive-rate", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    assert resp.json()["false_positive_rates"] == []
