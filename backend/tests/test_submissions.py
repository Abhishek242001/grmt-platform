import io

from tests.conftest import auth_headers, signup_and_login

FAKE_GRAMMAR_RESULT = {
    "check_type": "grammar",
    "result_json": {"issue_count": 0, "issues_per_1000_words": 0.0, "sample_issues": []},
    "score": 100.0,
    "pass_fail": None,
    "flagged": False,
    "model_version": "languagetool-latest",
}

FAKE_STRUCTURE_RESULT_CLEAN = {
    "check_type": "citation",
    "result_json": {"header_complete": True, "has_title": True, "has_authors": True, "has_abstract": True, "total_references_found": 10, "complete_references": 9},
    "score": 90.0,
    "pass_fail": True,
    "flagged": False,
    "model_version": "grobid-0.9.0-crf",
}

FAKE_STRUCTURE_RESULT_FAILING = {
    "check_type": "citation",
    "result_json": {"header_complete": False, "has_title": True, "has_authors": False, "has_abstract": True, "total_references_found": 2, "complete_references": 0},
    "score": 0.0,
    "pass_fail": False,
    "flagged": True,
    "model_version": "grobid-0.9.0-crf",
}


def _mock_checks(monkeypatch, grammar_result=None, structure_result=None):
    monkeypatch.setattr("app.routers.submissions.extract_text_from_pdf", lambda pdf_bytes: "Some extracted text.")
    monkeypatch.setattr("app.routers.submissions.check_grammar", lambda text: grammar_result or FAKE_GRAMMAR_RESULT)
    monkeypatch.setattr("app.routers.submissions.check_structure", lambda pdf_bytes: structure_result or FAKE_STRUCTURE_RESULT_CLEAN)


def _create_conference(client, token, gate_rules=None):
    resp = client.post("/api/conferences", json={"name": "Submission Test Conf"}, headers=auth_headers(token))
    conf_id = resp.json()["id"]
    if gate_rules is not None:
        client.put(f"/api/conferences/{conf_id}/gate-rules", json={"rules": gate_rules}, headers=auth_headers(token))
    return conf_id


def test_researcher_can_submit_paper(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)

    researcher_token = signup_and_login(client, email="researcher_sub@example.com", role="researcher")
    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "My Paper", "abstract": "An abstract", "track": "AI"}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ai_review_passed"
    assert body["conference_id"] == conf_id


def test_organizer_cannot_submit_paper(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub2@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Not Allowed", "abstract": "", "track": ""}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(org_token))
    assert resp.status_code == 403


def test_submission_to_nonexistent_conference_returns_404(client, monkeypatch):
    _mock_checks(monkeypatch)
    researcher_token = signup_and_login(client, email="researcher_404@example.com", role="researcher")
    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": "does-not-exist", "title": "Ghost Paper", "abstract": "", "track": ""}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    assert resp.status_code == 404


def test_researcher_can_view_own_submission(client, monkeypatch):
    _mock_checks(monkeypatch)
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


def test_researcher_cannot_view_another_researchers_submission(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub4@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    owner_token = signup_and_login(client, email="owner@example.com", role="researcher")
    other_token = signup_and_login(client, email="other@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Private Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(owner_token))
    sub_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/submissions/{sub_id}", headers=auth_headers(other_token))
    assert get_resp.status_code == 404


def test_ai_report_endpoint_returns_populated_checks_after_submission(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub5@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    researcher_token = signup_and_login(client, email="researcher_sub5@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "AI Checked Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    sub_id = create_resp.json()["id"]

    resp = client.get(f"/api/submissions/{sub_id}/ai-report", headers=auth_headers(researcher_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_status"] == "ai_review_passed"
    check_types = {c["check_type"] for c in body["checks"]}
    assert check_types == {"grammar", "citation"}


def test_hard_gate_failing_citation_check_hard_fails_submission(client, monkeypatch):
    _mock_checks(monkeypatch, structure_result=FAKE_STRUCTURE_RESULT_FAILING)
    org_token = signup_and_login(client, email="org_sub6@example.com", role="organizer")
    conf_id = _create_conference(
        client,
        org_token,
        gate_rules=[{"rule_type": "citation_completeness", "is_hard_gate": True, "threshold_hard": 50}],
    )
    researcher_token = signup_and_login(client, email="researcher_sub6@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Weak Citations Paper", "abstract": "", "track": ""}
    resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    assert resp.json()["status"] == "ai_review_hard_failed"


def test_file_url_endpoint_returns_signed_url(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub7@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    researcher_token = signup_and_login(client, email="researcher_sub7@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "File URL Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    sub_id = create_resp.json()["id"]

    resp = client.get(f"/api/submissions/{sub_id}/file-url", headers=auth_headers(researcher_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"].startswith("/api/files/")
    assert "expires_at" in body


def test_signed_file_url_actually_serves_the_uploaded_pdf(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub9@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    researcher_token = signup_and_login(client, email="researcher_sub9@example.com", role="researcher")

    original_bytes = b"%PDF-1.4 fake content for end-to-end retrieval test"
    files = {"file": ("paper.pdf", io.BytesIO(original_bytes), "application/pdf")}
    data = {"conference_id": conf_id, "title": "End To End File Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(researcher_token))
    sub_id = create_resp.json()["id"]

    url_resp = client.get(f"/api/submissions/{sub_id}/file-url", headers=auth_headers(researcher_token))
    signed_path = url_resp.json()["url"]

    file_resp = client.get(signed_path)
    assert file_resp.status_code == 200
    assert file_resp.content == original_bytes
    assert file_resp.headers["content-type"] == "application/pdf"


def test_files_endpoint_rejects_tampered_token(client):
    resp = client.get("/api/files/9999999999.deadbeef.submissions/does-not/exist/file.pdf")
    assert resp.status_code == 403


def test_file_url_endpoint_denies_other_researchers(client, monkeypatch):
    _mock_checks(monkeypatch)
    org_token = signup_and_login(client, email="org_sub8@example.com", role="organizer")
    conf_id = _create_conference(client, org_token)
    owner_token = signup_and_login(client, email="fileowner@example.com", role="researcher")
    other_token = signup_and_login(client, email="fileother@example.com", role="researcher")

    files = {"file": ("paper.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")}
    data = {"conference_id": conf_id, "title": "Guarded File Paper", "abstract": "", "track": ""}
    create_resp = client.post("/api/submissions", data=data, files=files, headers=auth_headers(owner_token))
    sub_id = create_resp.json()["id"]

    resp = client.get(f"/api/submissions/{sub_id}/file-url", headers=auth_headers(other_token))
    assert resp.status_code == 404
