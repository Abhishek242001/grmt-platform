import secrets
import time

# In-memory, single-use, short-lived tickets — the bridge between a normal
# REST-authenticated request and a WebSocket handshake, which can't carry an
# Authorization header. A ticket is minted by POST /api/ws/ticket (authenticated
# the normal way) and consumed exactly once when the socket connects.
_TICKET_TTL_SECONDS = 30
_tickets: dict[str, tuple[str, float]] = {}  # ticket -> (user_id, expires_at)


def issue_ticket(user_id: str) -> str:
    ticket = secrets.token_urlsafe(32)
    _tickets[ticket] = (user_id, time.time() + _TICKET_TTL_SECONDS)
    return ticket


def consume_ticket(ticket: str) -> str | None:
    entry = _tickets.pop(ticket, None)  # pop — single-use, always removed
    if entry is None:
        return None
    user_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return user_id
