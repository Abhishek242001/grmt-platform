"""update51 — tests for the researcher review-then-submit checkpoint.
Before this, evaluate_submission_gates advanced a clean pass straight to
"in_human_review" automatically; now it stops at "ai_review_passed" and
the researcher must explicitly call submit-for-review to advance, and a
hard-gate failure can never successfully reach that endpoint at all."""

import json


def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _db_session():
    from app.core import database as database_module
    return database_module.SessionLocal()


def _set_status_directly(submission_id, new_status):
    """Bypasses the real gate engine to put a submission into a specific
    status for testing the submit-for-review endpoint's own gating logic
    in isolation, independent of how that status was actually reached."""
    from app.models.submissions import Submission
    db = _db_session()
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        sub.status = new_status
        db.commit()
    finally:
        db.close()


def _create_submission(client, res_token, conf_id):
    r = client.post(
        "/api/submissions",
        json={
            "conference_id": conf_id, "title": "Paper",
            "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
        },
        headers=_auth(res_token),
    )
    return r.json()["id"]


def _setup(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_id = _create_submission(client, res_token, conf_id)
    return org_token, res_token, conf_id, sub_id


def test_submit_for_review_succeeds_when_ai_review_passed(client):
    org_token, res_token, conf_id, sub_id = _setup(client)
    _set_status_directly(sub_id, "ai_review_passed")

    r = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(res_token))
    assert r.status_code == 200
    assert r.json()["status"] == "in_human_review"


def test_submit_for_review_blocked_when_hard_failed(client):
    """The real safety property this whole feature exists for: a hard-gate
    failure must never be bypassable by just calling submit-for-review."""
    org_token, res_token, conf_id, sub_id = _setup(client)
    _set_status_directly(sub_id, "ai_review_hard_failed")

    r = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(res_token))
    assert r.status_code == 400
    assert "revise" in r.json()["detail"].lower() or "failed" in r.json()["detail"].lower()

    # and the submission must genuinely remain un-advanced, not just get a
    # rejected response while secretly moving forward anyway
    check = client.get(f"/api/submissions/{sub_id}", headers=_auth(res_token))
    assert check.json()["status"] == "ai_review_hard_failed"


def test_submit_for_review_blocked_while_still_processing(client):
    org_token, res_token, conf_id, sub_id = _setup(client)
    # Submission created with no upload/checks run — status stays at the
    # DB default, "submitted", never having reached "ai_review_passed".
    r = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(res_token))
    assert r.status_code == 400


def test_submit_for_review_is_not_repeatable(client):
    org_token, res_token, conf_id, sub_id = _setup(client)
    _set_status_directly(sub_id, "ai_review_passed")
    first = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(res_token))
    assert first.status_code == 200

    second = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(res_token))
    assert second.status_code == 400


def test_only_the_owning_researcher_can_submit_for_review(client):
    org_token, res_token, conf_id, sub_id = _setup(client)
    _set_status_directly(sub_id, "ai_review_passed")

    other_res = _signup(client, "other_res@example.com", role="researcher")
    r = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(other_res))
    assert r.status_code == 404


def test_organizer_cannot_call_submit_for_review(client):
    """This is specifically the researcher's own confirmation step —
    not something an organizer can do on the researcher's behalf."""
    org_token, res_token, conf_id, sub_id = _setup(client)
    _set_status_directly(sub_id, "ai_review_passed")

    r = client.post(f"/api/submissions/{sub_id}/submit-for-review", headers=_auth(org_token))
    assert r.status_code in (403, 404)
