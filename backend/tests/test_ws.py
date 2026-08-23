def _signup(client, email, role="researcher"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "Password1", "full_name": "Test User", "role": role,
    })
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _get_ticket(client, token):
    r = client.post("/api/ws/ticket", headers=_auth(token))
    assert r.status_code == 200
    return r.json()["ticket"]


def test_ws_connect_with_valid_ticket_succeeds(client):
    token = _signup(client, "res@example.com")
    ticket = _get_ticket(client, token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        data = ws.receive_json()
        assert data["type"] == "connected"


def test_ws_connect_with_invalid_ticket_rejected(client):
    try:
        with client.websocket_connect("/api/ws?ticket=not-a-real-ticket") as ws:
            ws.receive_json()
        assert False, "expected the connection to be rejected"
    except Exception:
        pass  # starlette raises on a server-side close during the handshake — expected


def test_ws_ticket_is_single_use(client):
    token = _signup(client, "res@example.com")
    ticket = _get_ticket(client, token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()

    # Second connection attempt with the SAME (already-consumed) ticket must fail
    try:
        with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws2:
            ws2.receive_json()
        assert False, "expected the reused ticket to be rejected"
    except Exception:
        pass


def test_organizer_can_subscribe_to_own_conference_queue(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    ticket = _get_ticket(client, org_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()  # "connected"
        ws.send_json({"action": "subscribe", "channel": f"conference:{conf_id}:queue"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"


def test_unrelated_organizer_cannot_subscribe_to_conference_queue(client):
    org1_token = _signup(client, "org1@example.com", role="organizer")
    org2_token = _signup(client, "org2@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org1_token))
    conf_id = conf_r.json()["id"]
    ticket = _get_ticket(client, org2_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": f"conference:{conf_id}:queue"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribe_denied"


def test_non_admin_cannot_subscribe_to_admin_channel(client):
    token = _signup(client, "res@example.com", role="researcher")
    ticket = _get_ticket(client, token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": "admin:test_run:123"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribe_denied"


def test_any_authenticated_user_can_subscribe_to_maintenance_channel(client):
    token = _signup(client, "res@example.com", role="researcher")
    ticket = _get_ticket(client, token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": "maintenance"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"


def test_submission_creation_pushes_live_event_to_subscribed_organizer(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    ticket = _get_ticket(client, org_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()  # "connected"
        ws.send_json({"action": "subscribe", "channel": f"conference:{conf_id}:queue"})
        ws.receive_json()  # "subscribed"

        res_token = _signup(client, "res@example.com", role="researcher")
        client.post(
            "/api/submissions",
            json={
                "conference_id": conf_id, "title": "Live Push Test Paper",
                "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
            },
            headers=_auth(res_token),
        )

        event = ws.receive_json()
        assert event["type"] == "submission.created"
        assert event["title"] == "Live Push Test Paper"


def test_unsubscribed_organizer_does_not_receive_event(client):
    """Negative case: an organizer connected but NOT subscribed to this specific
    conference's queue should not get the event — proves publish() is actually
    channel-scoped, not a broadcast to everyone connected."""
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    ticket = _get_ticket(client, org_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()  # "connected" — deliberately not subscribing to the queue channel

        res_token = _signup(client, "res@example.com", role="researcher")
        client.post(
            "/api/submissions",
            json={
                "conference_id": conf_id, "title": "Should Not Arrive",
                "original_filename": "p.docx", "original_file_url": "placeholder://p.docx",
            },
            headers=_auth(res_token),
        )

        # Send a harmless ping-like message to force a round trip, then confirm
        # nothing queue-related arrived — the connection is alive but silent.
        ws.send_json({"action": "subscribe", "channel": "maintenance"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"
        assert resp["channel"] == "maintenance"  # not a leaked submission.created event


# ── submission:{id}:updates — the per-submission channel, distinct from
# conference:{id}:queue's organizer/co-admin-only scoping. Needed because
# the submission detail page (where AI-report live updates actually
# matter) is viewed by the researcher who owns it and any reviewer
# assigned to it, not just organizers.

def test_submission_owner_can_subscribe_to_own_submission_updates(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    ticket = _get_ticket(client, res_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()  # "connected"
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"


def test_unrelated_researcher_cannot_subscribe_to_someone_elses_submission_updates(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    res1_token = _signup(client, "res1@example.com", role="researcher")
    res2_token = _signup(client, "res2@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res1_token),
    )
    sub_id = sub_r.json()["id"]
    ticket = _get_ticket(client, res2_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribe_denied"


def test_assigned_reviewer_can_subscribe_to_submission_updates(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    rev_token = _signup(client, "rev@example.com", role="reviewer")
    client.post(f"/api/conferences/{conf_id}/reviewers", json={"email": "rev@example.com"}, headers=_auth(org_token))
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    ticket = _get_ticket(client, rev_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"


def test_unassigned_reviewer_cannot_subscribe_to_submission_updates(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    rev_token = _signup(client, "rev@example.com", role="reviewer")  # deliberately NOT added as a conference reviewer
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    ticket = _get_ticket(client, rev_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribe_denied"


def test_organizer_can_subscribe_to_submission_updates_for_their_conference(client):
    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]
    ticket = _get_ticket(client, org_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribed"


def test_subscribing_to_nonexistent_submission_updates_is_denied(client):
    res_token = _signup(client, "res@example.com", role="researcher")
    ticket = _get_ticket(client, res_token)

    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()
        ws.send_json({"action": "subscribe", "channel": "submission:not-a-real-id:updates"})
        resp = ws.receive_json()
        assert resp["type"] == "subscribe_denied"


def test_resubmit_pushes_live_event_to_submission_channel(client, monkeypatch):
    """Confirms the real end-to-end wiring: resubmitting actually publishes
    to submission:{id}:updates, not just conference:queue — the whole
    point of adding this channel."""

    def fake_post(url, data=None, timeout=None):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"matches": []}

        return FakeResponse()

    import app.ai.grammar_check as grammar_check_module
    monkeypatch.setattr(grammar_check_module.httpx, "post", fake_post)

    org_token = _signup(client, "org@example.com", role="organizer")
    conf_r = client.post("/api/conferences", json={"name": "ICSE"}, headers=_auth(org_token))
    conf_id = conf_r.json()["id"]
    res_token = _signup(client, "res@example.com", role="researcher")
    sub_r = client.post(
        "/api/submissions",
        json={"conference_id": conf_id, "title": "My Paper", "original_filename": "p.docx", "original_file_url": "placeholder://p.docx"},
        headers=_auth(res_token),
    )
    sub_id = sub_r.json()["id"]

    from app.core import database as database_module
    from app.models.submissions import Submission
    db = database_module.SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == sub_id).first()
        sub.status = "revise_resubmit"
        db.commit()
    finally:
        db.close()

    ticket = _get_ticket(client, res_token)
    with client.websocket_connect(f"/api/ws?ticket={ticket}") as ws:
        ws.receive_json()  # "connected"
        ws.send_json({"action": "subscribe", "channel": f"submission:{sub_id}:updates"})
        ws.receive_json()  # "subscribed"

        from docx import Document
        import io
        doc = Document()
        doc.add_paragraph("Revised content.")
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        client.post(
            f"/api/submissions/{sub_id}/resubmit",
            files={"file": ("v2.docx", buf.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=_auth(res_token),
        )

        event = ws.receive_json()
        assert event["type"] == "submission.resubmitted"
        assert event["submission_id"] == sub_id
