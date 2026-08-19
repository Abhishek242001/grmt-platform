import io

from tests.conftest import auth_headers, signup_and_login


def _create_conference(client, token):
    resp = client.post("/api/conferences", json={"name": "Submission Test Conf"}, headers=auth_headers(token))
    return resp.json()["id"]


def test_researcher_can_submit_paper(client):
    org_token = signup_and_login(client, email="org_sub@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)

    researcher_token = signup_and_login(client, email="researcher_sub@example.com", role="researcher")
    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "My Paper", "abstract": "An abstract", "track": "AI"}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "processing"
    assert body["conference_id"] == conf_id


def test_organizer_cannot_submit_paper(client):
    org_token = signup_and_login(client, email="org_sub2@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Not Allowed", "abstract": "", "track": ""}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(org_token))
    assert resp.status_code == 403


def test_researcher_can_view_own_submission(client):
    org_token = signup_and_login(client, email="org_sub3@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    researcher_token = signup_and_login(client, email="researcher_sub3@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Owned Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    sub_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/submissions/{sub_id}", headers=auth_headers(researcher_token))
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Owned Paper"


def test_researcher_cannot_view_another_researchers_submission(client):
    org_token = signup_and_login(client, email="org_sub4@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    owner_token = signup_and_login(client, email="owner@example.com", role="researcher")
    other_token = signup_and_login(client, email="other@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Private Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(owner_token))
    sub_id = create_resp.json()["id"]

    # master doc §5.10 — 404, not 403, so existence isn't confirmed to a non-owner
    get_resp = client.get(f"/api/submissions/{sub_id}", headers=auth_headers(other_token))
    assert get_resp.status_code == 404


def test_ai_report_endpoint_returns_empty_checks_before_ai_pipeline_runs(client):
    org_token = signup_and_login(client, email="org_sub5@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    researcher_token = signup_and_login(client, email="researcher_sub5@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Pending AI Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    sub_id = create_resp.json()["id"]

    resp = client.get(f"/api/submissions/{sub_id}/ai-report", headers=auth_headers(researcher_token))
    assert resp.status_code == 200
    assert resp.json()["overall_status"] == "processing"
    assert resp.json()["checks"] == []  # AI orchestration not wired up in this starter codebase — see routers/submissions.py
