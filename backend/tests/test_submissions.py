def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_conference(client, org_token):
    r = client.post("/api/conferences", json={"name": "ICSE 2026"}, headers=_auth(org_token))
    return r.json()["id"]


def _submit(client, res_token, conf_id, title="Paper"):
    return client.post(
        "/api/submissions",
        json={
            "conference_id": conf_id, "title": title,
            "original_filename": "paper.docx", "original_file_url": "placeholder://uploads/paper.docx",
        },
        headers=_auth(res_token),
    )


def test_researcher_can_create_and_view_own_submission(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res_token = _signup(client, "res@example.com", role="researcher")

    r = _submit(client, res_token, conf_id, title="My Paper")
    assert r.status_code == 201
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(res_token))
    assert r.status_code == 200


def test_researcher_cannot_view_another_researchers_submission(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res1 = _signup(client, "res1@example.com", role="researcher")
    res2 = _signup(client, "res2@example.com", role="researcher")

    r = _submit(client, res1, conf_id, title="My Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(res2))
    assert r.status_code == 404


def test_researcher_cannot_view_another_researchers_ai_report(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res1 = _signup(client, "res1@example.com", role="researcher")
    res2 = _signup(client, "res2@example.com", role="researcher")

    r = _submit(client, res1, conf_id, title="My Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}/ai-report", headers=_auth(res2))
    assert r.status_code == 404


def test_conference_organizer_can_view_submissions_to_their_conference(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res_token = _signup(client, "res@example.com", role="researcher")

    r = _submit(client, res_token, conf_id, title="My Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(org_token))
    assert r.status_code == 200


def test_unrelated_organizer_cannot_view_submission(client):
    org1 = _signup(client, "org1@example.com", role="organizer")
    org2 = _signup(client, "org2@example.com", role="organizer")
    conf_id = _make_conference(client, org1)
    res_token = _signup(client, "res@example.com", role="researcher")

    r = _submit(client, res_token, conf_id, title="My Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(org2))
    assert r.status_code == 404


def test_assigned_reviewer_can_view_submission(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    rev_token = _signup(client, "rev@example.com", role="reviewer")
    conf_id = _make_conference(client, org_token)
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "rev@example.com"}, headers=_auth(org_token))

    res_token = _signup(client, "res@example.com", role="researcher")
    r = _submit(client, res_token, conf_id, title="Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(rev_token))
    assert r.status_code == 200


def test_unassigned_reviewer_cannot_view_submission(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    rev_token = _signup(client, "rev@example.com", role="reviewer")  # never assigned
    conf_id = _make_conference(client, org_token)

    res_token = _signup(client, "res@example.com", role="researcher")
    r = _submit(client, res_token, conf_id, title="Paper")
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(rev_token))
    assert r.status_code == 404


def test_researcher_can_list_own_submissions(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res_token = _signup(client, "res@example.com", role="researcher")
    _submit(client, res_token, conf_id, title="Paper 1")
    _submit(client, res_token, conf_id, title="Paper 2")

    r = client.get("/api/submissions/mine", headers=_auth(res_token))
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_create_submission_creates_initial_version(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res_token = _signup(client, "res@example.com", role="researcher")

    r = _submit(client, res_token, conf_id)
    assert r.status_code == 201
    sub_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}/history", headers=_auth(res_token))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["version_number"] == 1


def test_resubmit_requires_revise_resubmit_status(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res_token = _signup(client, "res@example.com", role="researcher")
    r = _submit(client, res_token, conf_id)
    sub_id = r.json()["id"]

    r = client.post(
        f"/api/submissions/{sub_id}/resubmit",
        json={"original_filename": "v2.docx", "original_file_url": "placeholder://uploads/v2.docx"},
        headers=_auth(res_token),
    )
    assert r.status_code == 400


def test_other_researcher_cannot_resubmit_someone_elses_paper(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_id = _make_conference(client, org_token)
    res1 = _signup(client, "res1@example.com", role="researcher")
    res2 = _signup(client, "res2@example.com", role="researcher")
    r = _submit(client, res1, conf_id)
    sub_id = r.json()["id"]

    r = client.post(
        f"/api/submissions/{sub_id}/resubmit",
        json={"original_filename": "v2.docx", "original_file_url": "placeholder://uploads/v2.docx"},
        headers=_auth(res2),
    )
    assert r.status_code == 404


def test_reviewer_sees_assigned_submissions_only(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    rev_token = _signup(client, "rev@example.com", role="reviewer")
    conf1 = _make_conference(client, org_token)
    conf2_r = client.post("/api/conferences", json={"name": "Other Conf"}, headers=_auth(org_token))
    conf2 = conf2_r.json()["id"]
    client.post(f"/api/conferences/{conf1}/reviewers", json={"email": "rev@example.com"}, headers=_auth(org_token))

    res_token = _signup(client, "res@example.com", role="researcher")
    _submit(client, res_token, conf1, title="In Assigned Conf")
    _submit(client, res_token, conf2, title="Not Assigned")

    r = client.get("/api/submissions/assigned", headers=_auth(rev_token))
    assert r.status_code == 200
    titles = [s["title"] for s in r.json()]
    assert titles == ["In Assigned Conf"]
