"""Tests for update51's per-submission reviewer assignment — the real gap
this closes: before this, any reviewer in a conference's general pool
(ConferenceReviewer) could review ANY submission in that conference. Now a
reviewer must be BOTH a pool member AND specifically assigned to that one
paper (SubmissionReviewerAssignment)."""


def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _me_id(client, token):
    return client.get("/api/auth/me", headers=_auth(token)).json()["id"]


def _setup_conference_with_pool_reviewer(client):
    """Organizer + conference + one reviewer already in the conference's
    pool — but crucially NOT yet assigned to any specific paper."""
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
    return org_token, rev_token, res_token, conf_id, sub_r.json()["id"]


def test_pool_member_not_assigned_to_this_paper_cannot_review_it(client):
    """The exact real gap this feature closes."""
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "accept"},
        headers=_auth(rev_token),
    )
    assert r.status_code == 404


def test_pool_member_not_assigned_cannot_even_view_the_submission(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(rev_token))
    assert r.status_code == 404


def test_organizer_can_assign_a_pool_member_to_a_specific_paper(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    r = client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))
    assert r.status_code == 201
    assert r.json()["reviewer_id"] == rev_id
    assert r.json()["submission_id"] == sub_id


def test_after_assignment_reviewer_can_view_and_review(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))

    view_r = client.get(f"/api/submissions/{sub_id}", headers=_auth(rev_token))
    assert view_r.status_code == 200

    review_r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "minor_revision", "comments": "Fix the intro."},
        headers=_auth(rev_token),
    )
    assert review_r.status_code == 201


def test_assigning_someone_outside_the_reviewer_pool_is_rejected(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    outsider = _signup(client, "outsider@example.com", role="reviewer")  # never invited to this conference
    outsider_id = _me_id(client, outsider)

    r = client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": outsider_id}, headers=_auth(org_token))
    assert r.status_code == 400


def test_non_organizer_cannot_assign_a_reviewer(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    other_org = _signup(client, "other_org@example.com", role="organizer")

    r = client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(other_org))
    assert r.status_code == 404


def test_researcher_cannot_assign_a_reviewer(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)

    r = client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(res_token))
    assert r.status_code in (403, 404)


def test_list_assigned_reviewers_shows_current_assignments(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))

    r = client.get(f"/api/submissions/{sub_id}/assigned-reviewers", headers=_auth(org_token))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["reviewer_id"] == rev_id


def test_unassigning_a_reviewer_revokes_their_access(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))

    del_r = client.delete(f"/api/submissions/{sub_id}/assign-reviewer/{rev_id}", headers=_auth(org_token))
    assert del_r.status_code == 204

    r = client.post(
        f"/api/submissions/{sub_id}/reviews",
        json={"recommendation": "accept"},
        headers=_auth(rev_token),
    )
    assert r.status_code == 404


def test_assigning_twice_is_idempotent_not_duplicated(client):
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)
    rev_id = _me_id(client, rev_token)
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))

    r = client.get(f"/api/submissions/{sub_id}/assigned-reviewers", headers=_auth(org_token))
    assert len(r.json()) == 1


def test_assigned_endpoint_returns_only_this_reviewers_actual_papers(client):
    """GET /api/submissions/assigned — update51 tightened this from "every
    paper in every conference I'm a pool member of" to "papers actually
    assigned to me"."""
    org_token, rev_token, res_token, conf_id, sub_id = _setup_conference_with_pool_reviewer(client)

    # A second submission in the SAME conference, which rev_token is a pool
    # member of but will never be assigned to.
    other_sub_r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_id, "title": "Other Paper",
            "original_filename": "p2.docx", "original_file_url": "placeholder://p2.docx",
        },
        headers=_auth(res_token),
    )
    other_sub_id = other_sub_r.json()["id"]

    rev_id = _me_id(client, rev_token)
    client.post(f"/api/submissions/{sub_id}/assign-reviewer", json={"reviewer_id": rev_id}, headers=_auth(org_token))
    # deliberately NOT assigning rev_token to other_sub_id

    r = client.get("/api/submissions/assigned", headers=_auth(rev_token))
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()]
    assert sub_id in ids
    assert other_sub_id not in ids
