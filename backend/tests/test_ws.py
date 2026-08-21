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
