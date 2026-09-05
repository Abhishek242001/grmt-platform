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


# ── pdf-stream — the endpoint the signed URL actually points at ────
#
# Everything above only checks that a signed-URL-SHAPED string comes
# back. These confirm the URL is genuinely fetchable and serves real
# bytes — the actual gap that made a PDF viewer impossible to build
# against until fixed.

def _setup_with_real_pdf(client, tmp_path):
    """Like _setup(), but with a genuine converted_pdf_url pointing at a
    real PDF on disk — the placeholder data _setup() uses (converted_pdf_url
    left None, original_file_url a fake 'placeholder://...' string) can
    never actually be streamed, on purpose (see stream_pdf's docstring)."""
    import pymupdf

    from app.core import database as database_module
    from app.models.submissions import SubmissionVersion

    org_token, rev_token, res_token, sub_id, version_id = _setup(client)

    pdf_path = str(tmp_path / "real.pdf")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Real PDF content for streaming test.")
    doc.save(pdf_path)
    doc.close()

    db = database_module.SessionLocal()
    try:
        version = db.query(SubmissionVersion).filter(SubmissionVersion.id == version_id).first()
        version.converted_pdf_url = pdf_path
        db.commit()
    finally:
        db.close()

    return org_token, rev_token, res_token, sub_id, version_id


def test_pdf_url_is_genuinely_fetchable_and_serves_real_bytes(client, tmp_path):
    _, _, res_token, _, version_id = _setup_with_real_pdf(client, tmp_path)

    r = client.get(f"/api/submissions/versions/{version_id}/pdf-url", headers=_auth(res_token))
    signed_url = r.json()["url"]
    assert signed_url.startswith(f"/api/submissions/versions/{version_id}/pdf-stream?")

    # No Authorization header on this request — matches how a browser's
    # native PDF viewer would actually fetch it (can't attach custom
    # headers), and confirms the signature alone is sufficient auth.
    stream_r = client.get(signed_url)
    assert stream_r.status_code == 200
    assert stream_r.headers["content-type"] == "application/pdf"
    assert stream_r.content.startswith(b"%PDF")


def test_pdf_stream_rejects_tampered_signature(client, tmp_path):
    _, _, res_token, _, version_id = _setup_with_real_pdf(client, tmp_path)

    r = client.get(f"/api/submissions/versions/{version_id}/pdf-url", headers=_auth(res_token))
    signed_url = r.json()["url"]
    tampered = signed_url[:-1] + ("0" if signed_url[-1] != "0" else "1")

    stream_r = client.get(tampered)
    assert stream_r.status_code == 403


def test_pdf_stream_rejects_expired_signature(client, tmp_path):
    from app.core.file_signing import generate_signed_url

    _, _, res_token, _, version_id = _setup_with_real_pdf(client, tmp_path)

    # Signature valid in shape but for a timestamp already in the past —
    # confirms expiry is actually enforced, not just present in the string.
    import hashlib
    import hmac
    import time

    from app.core.config import settings

    expired = int(time.time()) - 10
    payload = f"{version_id}:{expired}"
    sig = hmac.new(settings.file_signing_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    stream_r = client.get(f"/api/submissions/versions/{version_id}/pdf-stream?expires={expired}&signature={sig}")
    assert stream_r.status_code == 403


def test_pdf_stream_404s_when_no_real_pdf_exists_yet(client):
    """Uses the plain _setup() (placeholder data, no real converted PDF) —
    the signed URL is still issued (matches the existing contract), but
    actually fetching it correctly reports "not available" rather than
    serving garbage or crashing."""
    _, _, res_token, _, version_id = _setup(client)

    r = client.get(f"/api/submissions/versions/{version_id}/pdf-url", headers=_auth(res_token))
    signed_url = r.json()["url"]

    stream_r = client.get(signed_url)
    assert stream_r.status_code == 404
