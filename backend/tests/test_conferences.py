from tests.conftest import auth_headers, signup_and_login


def test_organizer_can_create_conference(client):
    token = signup_and_login(client, email="org@example.com", role="organizer")
    resp = client.post("/api/conferences", json={"name": "Test Conf 2026", "theme": "AI"}, headers=auth_headers(token))
    assert resp.status_code == 201
    assert resp.json()["name"] == "Test Conf 2026"


def test_researcher_cannot_create_conference(client):
    token = signup_and_login(client, email="researcher@example.com", role="researcher")
    resp = client.post("/api/conferences", json={"name": "Should Fail"}, headers=auth_headers(token))
    assert resp.status_code == 403


def test_gate_rules_reject_hard_ai_content_gate_via_api(client):
    """This is the API-layer enforcement of master doc §5.2 / development_rule.md's core constraint."""
    token = signup_and_login(client, email="org2@example.com", role="organizer")
    conf_resp = client.post("/api/conferences", json={"name": "Gate Test Conf"}, headers=auth_headers(token))
    conf_id = conf_resp.json()["id"]

    resp = client.put(
        f"/api/conferences/{conf_id}/gate-rules",
        json={"rules": [{"rule_type": "ai_content_pct", "is_hard_gate": True, "threshold_hard": 20}]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"]["code"] == "GATE_RULE_INVALID"


def test_gate_rules_accept_valid_soft_gate_via_api(client):
    token = signup_and_login(client, email="org3@example.com", role="organizer")
    conf_resp = client.post("/api/conferences", json={"name": "Valid Gate Conf"}, headers=auth_headers(token))
    conf_id = conf_resp.json()["id"]

    resp = client.put(
        f"/api/conferences/{conf_id}/gate-rules",
        json={"rules": [{"rule_type": "ai_content_pct", "is_hard_gate": False, "threshold_soft": 15}]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 1

    get_resp = client.get(f"/api/conferences/{conf_id}/gate-rules", headers=auth_headers(token))
    assert get_resp.status_code == 200
    assert get_resp.json()[0]["rule_type"] == "ai_content_pct"
    assert get_resp.json()[0]["is_hard_gate"] is False


def test_get_nonexistent_conference_returns_404(client):
    token = signup_and_login(client, email="org4@example.com", role="organizer")
    resp = client.get("/api/conferences/does-not-exist", headers=auth_headers(token))
    assert resp.status_code == 404


def test_list_conferences_requires_auth(client):
    resp = client.get("/api/conferences")
    assert resp.status_code == 401
