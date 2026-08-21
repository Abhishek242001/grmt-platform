def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_submission_with_reviewer(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]

    rev_token = _signup(client, "rev@example.com", role="reviewer")
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "rev@example.com"}, headers=_auth(org_token))

    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_id, "title": "Paper",
            "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
        },
        headers=_auth(res_token),
    )
    return org_token, rev_token, res_token, sub_r.json()["id"]


def test_assigned_reviewer_can_submit_review(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "accept", "comments": "Solid work."},
        headers=_auth(rev_token),
    )
    assert r.status_code == 201
    assert r.json()["recommendation"] == "accept"


def test_unassigned_reviewer_cannot_submit_review(client):
    org_token, _, res_token, sub_id = _setup_submission_with_reviewer(client)
    other_rev = _signup(client, "other_rev@example.com", role="reviewer")  # never assigned
    r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "accept"},
        headers=_auth(other_rev),
    )
    assert r.status_code == 404


def test_invalid_recommendation_rejected(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "maybe"},
        headers=_auth(rev_token),
    )
    assert r.status_code == 422


def test_reviewer_sees_only_own_review_not_others(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    client.post(f"/api/submissions/{sub_id}/reviews", json={"recommendation": "accept"}, headers=_auth(rev_token))

    rev2 = _signup(client, "rev2@example.com", role="reviewer")
    conf_r = client.get(f"/api/submissions/{sub_id}", headers=_auth(org_token))
    conf_id = conf_r.json()["conference_id"]
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "rev2@example.com"}, headers=_auth(org_token))
    client.post(f"/api/submissions/{sub_id}/reviews", json={"recommendation": "reject"}, headers=_auth(rev2))

    r = client.get(f"/api/submissions/{sub_id}/reviews", headers=_auth(rev_token))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["recommendation"] == "accept"


def test_organizer_sees_all_reviews(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    client.post(f"/api/submissions/{sub_id}/reviews", json={"recommendation": "accept"}, headers=_auth(rev_token))

    r = client.get(f"/api/submissions/{sub_id}/reviews", headers=_auth(org_token))
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_researcher_cannot_see_raw_reviews(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    client.post(f"/api/submissions/{sub_id}/reviews", json={"recommendation": "accept"}, headers=_auth(rev_token))

    r = client.get(f"/api/submissions/{sub_id}/reviews", headers=_auth(res_token))
    assert r.status_code == 404


def test_organizer_can_make_decision_and_it_updates_submission_status(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    r = client.post(
        f"/api/submissions/{sub_id}/decision",
        json={"decision": "accept", "notes": "Great paper."},
        headers=_auth(org_token),
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "accept"

    sub_r = client.get(f"/api/submissions/{sub_id}", headers=_auth(res_token))
    assert sub_r.json()["status"] == "accepted"


def test_unrelated_organizer_cannot_make_decision(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    other_org = _signup(client, "other_org@example.com", role="organizer")
    r = client.post(
        f"/api/submissions/{sub_id}/decision",
        json={"decision": "reject"},
        headers=_auth(other_org),
    )
    assert r.status_code == 404


def test_researcher_can_view_decision_once_made(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    client.post(f"/api/submissions/{sub_id}/decision", json={"decision": "reject"}, headers=_auth(org_token))

    r = client.get(f"/api/submissions/{sub_id}/decision", headers=_auth(res_token))
    assert r.status_code == 200
    assert r.json()["decision"] == "reject"


def test_decision_not_found_before_one_is_made(client):
    org_token, rev_token, res_token, sub_id = _setup_submission_with_reviewer(client)
    r = client.get(f"/api/submissions/{sub_id}/decision", headers=_auth(res_token))
    assert r.status_code == 404
