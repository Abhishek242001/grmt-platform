def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]

    rev_token = _signup(client, "rev@example.com", role="reviewer")
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "rev@example.com"}, headers=_auth(org_token))

    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]

    hist_r = client.get(f"/api/submissions/{sub_id}/history", headers=_auth(res_token))
    version_id = hist_r.json()[0]["id"]
    return org_token, rev_token, res_token, sub_id, version_id


def test_owner_researcher_gets_signed_pdf_url(client):
    _, _, res_token, _, version_id = _setup(client)
    r = client.get(f"/api/submissions/versions/{version_id}/pdf-url", headers=_auth(res_token))
    assert r.status_code == 200
    assert "signature=" in r.json()["url"]
    assert "expires=" in r.json()["url"]


def test_unrelated_user_cannot_get_signed_url(client):
    _, _, _, _, version_id = _setup(client)
    other_res = _signup(client, "other@example.com", role="researcher")
    r = client.get(f"/api/submissions/versions/{version_id}/pdf-url", headers=_auth(other_res))
    assert r.status_code == 404


def test_reviewer_can_create_annotation(client):
    _, rev_token, _, _, version_id = _setup(client)
    r = client.post(
        f"/api/submissions/versions/{version_id}/annotations",
        json={"page_number": 1, "position_json": '{"x":10,"y":20}', "color": "yellow", "comment": "Check this citation"},
        headers=_auth(rev_token),
    )
    assert r.status_code == 201
    assert r.json()["comment"] == "Check this citation"


def test_researcher_cannot_create_annotation(client):
    _, _, res_token, _, version_id = _setup(client)
    r = client.post(
        f"/api/submissions/versions/{version_id}/annotations",
        json={"page_number": 1, "position_json": '{"x":10,"y":20}'},
        headers=_auth(res_token),
    )
    assert r.status_code == 403


def test_annotation_creator_can_delete_own_annotation(client):
    _, rev_token, _, _, version_id = _setup(client)
    r = client.post(
        f"/api/submissions/versions/{version_id}/annotations",
        json={"page_number": 1, "position_json": '{"x":10,"y":20}'},
        headers=_auth(rev_token),
    )
    annotation_id = r.json()["id"]

    r = client.delete(f"/api/submissions/annotations/{annotation_id}", headers=_auth(rev_token))
    assert r.status_code == 204


def test_other_reviewer_cannot_delete_someone_elses_annotation(client):
    org_token, rev_token, _, sub_id, version_id = _setup(client)
    r = client.post(
        f"/api/submissions/versions/{version_id}/annotations",
        json={"page_number": 1, "position_json": '{"x":10,"y":20}'},
        headers=_auth(rev_token),
    )
    annotation_id = r.json()["id"]

    r = client.get(f"/api/submissions/{sub_id}", headers=_auth(org_token))
    conf_id = r.json()["conference_id"]
    other_rev = _signup(client, "other_rev@example.com", role="reviewer")
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "other_rev@example.com"}, headers=_auth(org_token))

    r = client.delete(f"/api/submissions/annotations/{annotation_id}", headers=_auth(other_rev))
    assert r.status_code == 404
