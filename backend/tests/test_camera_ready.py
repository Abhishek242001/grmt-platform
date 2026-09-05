"""update51 — camera-ready paper submission, only reachable once a
Decision.decision == "accept" exists for the submission. Copyright
transfer file is optional."""


def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_accepted_submission(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]

    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_id, "title": "Paper",
            "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
        },
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]

    client.post(f"/api/submissions/{sub_id}/decision", json={"decision": "accept"}, headers=_auth(org_token))
    return org_token, res_token, sub_id


def test_camera_ready_upload_succeeds_after_acceptance(client):
    org_token, res_token, sub_id = _setup_accepted_submission(client)
    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        headers=_auth(res_token),
    )
    assert r.status_code == 200
    assert r.json()["camera_ready_file_url"] is not None
    assert r.json()["copyright_transfer_file_url"] is None


def test_camera_ready_upload_creates_a_new_version_visible_to_the_viewer(client):
    """update52 — the real fix: camera-ready used to just set a bare path
    on Submission with no way for the main PDF viewer to ever show it. The
    viewer always shows the LATEST SubmissionVersion (history[-1] on the
    frontend, ordered by version_number) — so camera-ready must create a
    real new version to actually become visible there, which is the whole
    point (organizer/researcher should see the final camera-ready paper,
    not the original submitted draft, once it's been uploaded)."""
    org_token, res_token, sub_id = _setup_accepted_submission(client)

    before = client.get(f"/api/submissions/{sub_id}/history", headers=_auth(res_token)).json()
    assert len(before) == 1  # just the original v1 at this point

    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 camera ready content", "application/pdf")},
        headers=_auth(res_token),
    )
    assert r.status_code == 200

    after = client.get(f"/api/submissions/{sub_id}/history", headers=_auth(res_token)).json()
    assert len(after) == 2  # original v1 + the new camera-ready v2
    latest = after[-1]
    assert latest["version_number"] == 2
    assert latest["original_filename"] == "final.pdf"


def test_camera_ready_upload_does_not_retrigger_ai_checks(client):
    """Camera-ready is post-acceptance — re-running grammar/citation/etc.
    checks against it serves no purpose and must not happen."""
    org_token, res_token, sub_id = _setup_accepted_submission(client)

    before = client.get(f"/api/submissions/{sub_id}/ai-report", headers=_auth(res_token)).json()

    client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 camera ready content", "application/pdf")},
        headers=_auth(res_token),
    )

    after = client.get(f"/api/submissions/{sub_id}/ai-report", headers=_auth(res_token)).json()
    assert len(after) == len(before)  # no new AIReport rows from camera-ready


def test_camera_ready_upload_with_optional_copyright_transfer(client):
    org_token, res_token, sub_id = _setup_accepted_submission(client)
    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={
            "file": ("final.pdf", b"%PDF-1.4 fake content", "application/pdf"),
            "copyright_transfer_file": ("copyright.pdf", b"%PDF-1.4 signed copyright", "application/pdf"),
        },
        headers=_auth(res_token),
    )
    assert r.status_code == 200
    assert r.json()["camera_ready_file_url"] is not None
    assert r.json()["copyright_transfer_file_url"] is not None


def test_camera_ready_blocked_before_acceptance(client):
    org_token = _signup(client, "org2@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE2"}, headers=_auth(org_token))
    res_token = _signup(client, "res2@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_r.json()["id"], "title": "Paper",
            "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
        },
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    # deliberately no Decision made yet

    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        headers=_auth(res_token),
    )
    assert r.status_code == 400


def test_camera_ready_blocked_after_rejection(client):
    org_token = _signup(client, "org3@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE3"}, headers=_auth(org_token))
    res_token = _signup(client, "res3@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_r.json()["id"], "title": "Paper",
            "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
        },
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    client.post(f"/api/submissions/{sub_id}/decision", json={"decision": "reject"}, headers=_auth(org_token))

    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        headers=_auth(res_token),
    )
    assert r.status_code == 400


def test_only_owning_researcher_can_submit_camera_ready(client):
    org_token, res_token, sub_id = _setup_accepted_submission(client)
    other_res = _signup(client, "other_res@example.com", role="researcher")

    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        headers=_auth(other_res),
    )
    assert r.status_code == 404


def test_camera_ready_rejects_disallowed_file_extension(client):
    org_token, res_token, sub_id = _setup_accepted_submission(client)
    r = client.post(
        f"/api/submissions/{sub_id}/camera-ready",
        files={"file": ("final.exe", b"not a paper", "application/octet-stream")},
        headers=_auth(res_token),
    )
    assert r.status_code == 400
