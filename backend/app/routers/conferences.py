from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer, GateRule
from app.models.submissions import Submission
from app.models.core import User
from app.schemas.submissions import SubmissionOut
from app.schemas.conferences import (
    ConferenceCreate,
    ConferenceOut,
    ConferenceUpdate,
    CoAdminOut,
    GateRuleIn,
    GateRuleOut,
    MemberInvite,
    ReviewerOut,
)

router = APIRouter(prefix="/api/conferences", tags=["conferences"])


def _is_coadmin(conference_id: str, user_id: str, db: Session) -> bool:
    return (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == conference_id, ConferenceCoAdmin.user_id == user_id)
        .first()
        is not None
    )


def _get_owned_conference_or_404(conference_id: str, user: User, db: Session) -> Conference:
    """Ownership check shared by every organizer-only endpoint below. A platform_admin
    bypasses it; the conference's own organizer OR a co-admin added to that specific
    conference pass; anyone else — including another organizer entirely — gets 404,
    not 403, so they can't even confirm the conference exists."""
    conf = db.query(Conference).filter(Conference.id == conference_id).first()
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")
    is_owner = conf.organizer_id == user.id
    is_admin = user.role == "platform_admin"
    if not (is_owner or is_admin or _is_coadmin(conference_id, user.id, db)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")
    return conf


def _find_user_by_email_or_400(email: str, db: Session) -> User:
    user = db.query(User).filter(User.email == email.lower()).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No account exists with that email")
    return user


@router.post("", response_model=ConferenceOut, status_code=status.HTTP_201_CREATED)
def create_conference(
    payload: ConferenceCreate,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    conf = Conference(organizer_id=user.id, **payload.model_dump())
    db.add(conf)
    db.commit()
    db.refresh(conf)
    return conf


@router.get("", response_model=list[ConferenceOut])
def list_conferences(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Conference).all()


@router.get("/{conference_id}", response_model=ConferenceOut)
def get_conference(conference_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    conf = db.query(Conference).filter(Conference.id == conference_id).first()
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")
    return conf


@router.patch("/{conference_id}", response_model=ConferenceOut)
def update_conference(
    conference_id: str,
    payload: ConferenceUpdate,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    conf = _get_owned_conference_or_404(conference_id, user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(conf, field, value)
    db.commit()
    db.refresh(conf)
    return conf


@router.get("/{conference_id}/gate-rules", response_model=list[GateRuleOut])
def get_gate_rules(
    conference_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    return db.query(GateRule).filter(GateRule.conference_id == conference_id).all()


@router.put("/{conference_id}/gate-rules", response_model=list[GateRuleOut])
def update_gate_rules(
    conference_id: str,
    payload: list[GateRuleIn],
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    for rule_in in payload:
        existing = (
            db.query(GateRule)
            .filter(GateRule.conference_id == conference_id, GateRule.check_type == rule_in.check_type)
            .first()
        )
        if existing:
            existing.is_hard_gate = rule_in.is_hard_gate
            existing.threshold = rule_in.threshold
        else:
            db.add(GateRule(conference_id=conference_id, **rule_in.model_dump()))
    db.commit()
    return db.query(GateRule).filter(GateRule.conference_id == conference_id).all()


# ── Co-admins ────────────────────────────────────────────────────────────────

@router.get("/{conference_id}/coadmins", response_model=list[CoAdminOut])
def list_coadmins(
    conference_id: str, user: User = Depends(require_role("organizer", "platform_admin")), db: Session = Depends(get_db)
):
    _get_owned_conference_or_404(conference_id, user, db)
    rows = db.query(ConferenceCoAdmin).filter(ConferenceCoAdmin.conference_id == conference_id).all()
    out = []
    for row in rows:
        u = db.query(User).filter(User.id == row.user_id).first()
        out.append(CoAdminOut(id=row.id, user_id=row.user_id, email=u.email, full_name=u.full_name))
    return out


@router.post("/{conference_id}/coadmins", response_model=CoAdminOut, status_code=status.HTTP_201_CREATED)
def add_coadmin(
    conference_id: str,
    payload: MemberInvite,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    target = _find_user_by_email_or_400(payload.email, db)
    if target.role not in ("organizer", "platform_admin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Co-admins must have an organizer account")

    existing = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == conference_id, ConferenceCoAdmin.user_id == target.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a co-admin")

    row = ConferenceCoAdmin(conference_id=conference_id, user_id=target.id, added_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return CoAdminOut(id=row.id, user_id=target.id, email=target.email, full_name=target.full_name)


@router.delete("/{conference_id}/coadmins/{coadmin_row_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_coadmin(
    conference_id: str,
    coadmin_row_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    row = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.id == coadmin_row_id, ConferenceCoAdmin.conference_id == conference_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Co-admin not found")
    db.delete(row)
    db.commit()


# ── Reviewers ────────────────────────────────────────────────────────────────

@router.get("/{conference_id}/reviewers", response_model=list[ReviewerOut])
def list_reviewers(
    conference_id: str, user: User = Depends(require_role("organizer", "platform_admin")), db: Session = Depends(get_db)
):
    _get_owned_conference_or_404(conference_id, user, db)
    rows = db.query(ConferenceReviewer).filter(ConferenceReviewer.conference_id == conference_id).all()
    out = []
    for row in rows:
        u = db.query(User).filter(User.id == row.reviewer_id).first()
        out.append(ReviewerOut(id=row.id, reviewer_id=row.reviewer_id, email=u.email, full_name=u.full_name))
    return out


@router.post("/{conference_id}/reviewers", response_model=ReviewerOut, status_code=status.HTTP_201_CREATED)
def add_reviewer(
    conference_id: str,
    payload: MemberInvite,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    target = _find_user_by_email_or_400(payload.email, db)
    if target.role != "reviewer":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That account is not registered as a reviewer")

    existing = (
        db.query(ConferenceReviewer)
        .filter(ConferenceReviewer.conference_id == conference_id, ConferenceReviewer.reviewer_id == target.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already a reviewer on this conference")

    row = ConferenceReviewer(conference_id=conference_id, reviewer_id=target.id, invited_by=user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return ReviewerOut(id=row.id, reviewer_id=target.id, email=target.email, full_name=target.full_name)


@router.delete("/{conference_id}/reviewers/{reviewer_row_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_reviewer(
    conference_id: str,
    reviewer_row_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    row = (
        db.query(ConferenceReviewer)
        .filter(ConferenceReviewer.id == reviewer_row_id, ConferenceReviewer.conference_id == conference_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reviewer not found")
    db.delete(row)
    db.commit()

@router.get("/{conference_id}/submissions", response_model=list[SubmissionOut])
def conference_submission_queue(
    conference_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)
    return db.query(Submission).filter(Submission.conference_id == conference_id).all()
