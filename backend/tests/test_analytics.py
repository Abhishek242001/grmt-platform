def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_organizer_sees_analytics_for_own_conference(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]

    res_token = _signup(client, "res@example.com", role="researcher")
    client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )

    r = client.get(f"/api/conferences/{conf_id}/analytics", headers=_auth(org_token))
    assert r.status_code == 200
    body = r.json()
    assert body["total_submissions"] == 1
    assert body["submissions_by_status"]["submitted"] == 1
    assert body["total_reviews_submitted"] == 0


def test_unrelated_organizer_cannot_see_analytics(client):
    org1 = _signup(client, "org1@example.com", role="organizer")
    org2 = _signup(client, "org2@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org1))
    conf_id = conf_r.json()["id"]

    r = client.get(f"/api/conferences/{conf_id}/analytics", headers=_auth(org2))
    assert r.status_code == 404


def test_analytics_on_empty_conference_no_division_error(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]

    r = client.get(f"/api/conferences/{conf_id}/analytics", headers=_auth(org_token))
    assert r.status_code == 200
    assert r.json()["total_submissions"] == 0
    assert r.json()["average_reviews_per_submission"] == 0.0
