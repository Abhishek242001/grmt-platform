from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.ws_manager import get_manager
from app.core.ws_tickets import consume_ticket, issue_ticket
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer
from app.models.core import User
from app.schemas.ws import TicketOut

router = APIRouter(prefix="/api/ws", tags=["websocket"])

_TICKET_TTL_SECONDS = 30


@router.post("/ticket", response_model=TicketOut)
def get_ws_ticket(user: User = Depends(get_current_user)):
    ticket = issue_ticket(user.id)
    return TicketOut(ticket=ticket, expires_in_seconds=_TICKET_TTL_SECONDS)


def _authorize_channel(channel: str, user: User, db: Session) -> bool:
    if channel == f"user:{user.id}:notifications":
        return True

    if channel.startswith("conference:") and channel.endswith(":queue"):
        conference_id = channel.split(":")[1]
        if user.role == "platform_admin":
            return True
        conf = db.query(Conference).filter(Conference.id == conference_id).first()
        if conf and conf.organizer_id == user.id:
            return True
        is_coadmin = (
            db.query(ConferenceCoAdmin)
            .filter(ConferenceCoAdmin.conference_id == conference_id, ConferenceCoAdmin.user_id == user.id)
            .first() is not None
        )
        return is_coadmin

    if channel.startswith("submission:") and channel.endswith(":updates"):
        # Distinct from conference:{id}:queue above on purpose — that
        # channel is organizer/co-admin only (it fans out every submission
        # in the conference, appropriate for a queue-overview page but a
        # real over-exposure if a researcher or reviewer could subscribe to
        # it just to watch their own one submission). This channel is
        # scoped to exactly one submission, so a researcher (submission
        # owner) and any reviewer actually assigned to it can subscribe too
        # — needed for the submission detail page's live AI-report updates,
        # which researchers and reviewers view just as much as organizers.
        from app.models.submissions import Submission

        submission_id = channel.split(":")[1]
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if sub is None:
            return False
        if user.role == "platform_admin":
            return True
        if sub.researcher_id == user.id:
            return True
        conf = db.query(Conference).filter(Conference.id == sub.conference_id).first()
        if conf and conf.organizer_id == user.id:
            return True
        is_coadmin = (
            db.query(ConferenceCoAdmin)
            .filter(ConferenceCoAdmin.conference_id == sub.conference_id, ConferenceCoAdmin.user_id == user.id)
            .first() is not None
        )
        if is_coadmin:
            return True
        is_assigned_reviewer = (
            db.query(ConferenceReviewer)
            .filter(ConferenceReviewer.conference_id == sub.conference_id, ConferenceReviewer.reviewer_id == user.id)
            .first() is not None
        )
        return is_assigned_reviewer

    if channel.startswith("admin:"):
        return user.role == "platform_admin"

    if channel == "maintenance":
        return True

    return False


@router.websocket("")
async def ws_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    # Using Depends(get_db) here — same as every REST endpoint — is what lets
    # conftest.py's test-database override apply to WebSocket connections too.
    # Manually instantiating SessionLocal() here previously bypassed that override
    # entirely, silently querying the real dev DB instead of the test DB.
    ticket = websocket.query_params.get("ticket")
    user_id = consume_ticket(ticket) if ticket else None
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    manager = get_manager()
    await manager.connect(websocket, user_id)
    await websocket.send_json({"type": "connected", "user_id": user_id})

    try:
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            channel = msg.get("channel")

            if action == "subscribe" and channel:
                if _authorize_channel(channel, user, db):
                    await manager.subscribe(websocket, channel)
                    await websocket.send_json({"type": "subscribed", "channel": channel})
                else:
                    await websocket.send_json({"type": "subscribe_denied", "channel": channel})
            elif action == "unsubscribe" and channel:
                await manager.unsubscribe(websocket, channel)
                await websocket.send_json({"type": "unsubscribed", "channel": channel})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
