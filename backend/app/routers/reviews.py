from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer
from app.models.core import User
from app.models.submissions import Decision, Review, Submission, SubmissionReviewerAssignment
from app.schemas.reviews import (
    AssignReviewerIn,
    DecisionIn,
    DecisionOut,
    ReviewerAssignmentOut,
    ReviewIn,
    ReviewOut,
)

router = APIRouter(prefix="/api/submissions", tags=["reviews"])


def _get_submission_or_404(submission_id: str, db: Session) -> Submission:
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return sub


def _require_assigned_reviewer(submission: Submission, user: User, db: Session) -> None:
    """update51 — now requires BOTH: still a pool member for this
    conference (ConferenceReviewer — the invite), AND specifically
    assigned to THIS paper (SubmissionReviewerAssignment — the
    organizer's per-paper allocation). Before this change, any pool
    member could review any submission in the conference; see
    SubmissionReviewerAssignment's docstring in models/submissions.py."""
    is_pool_member = (
        db.query(ConferenceReviewer)
        .filter(
            ConferenceReviewer.conference_id == submission.conference_id,
            ConferenceReviewer.reviewer_id == user.id,
        )
        .first()
        is not None
    )
    is_assigned_this_paper = (
        db.query(SubmissionReviewerAssignment)
        .filter(
            SubmissionReviewerAssignment.submission_id == submission.id,
            SubmissionReviewerAssignment.reviewer_id == user.id,
        )
        .first()
        is not None
    )
    if not (is_pool_member and is_assigned_this_paper):
        # 404, not 403 — same pattern used everywhere else: don't confirm the
        # submission exists to someone with no legitimate reason to know.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")


def _is_conference_organizer_or_admin(submission: Submission, user: User, db: Session) -> bool:
    if user.role == "platform_admin":
        return True
    conf = db.query(Conference).filter(Conference.id == submission.conference_id).first()
    if conf and conf.organizer_id == user.id:
        return True
    is_coadmin = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == submission.conference_id, ConferenceCoAdmin.user_id == user.id)
        .first()
        is not None
    )
    return is_coadmin


@router.post("/{submission_id}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def submit_review(
    submission_id: str,
    payload: ReviewIn,
    user: User = Depends(require_role("reviewer")),
    db: Session = Depends(get_db),
):
    sub = _get_submission_or_404(submission_id, db)
    _require_assigned_reviewer(sub, user, db)

    existing = (
        db.query(Review)
        .filter(Review.submission_id == submission_id, Review.reviewer_id == user.id)
        .first()
    )
    if existing:
        existing.recommendation = payload.recommendation
        existing.comments = payload.comments
        db.commit()
        db.refresh(existing)
        return existing

    review = Review(submission_id=submission_id, reviewer_id=user.id, **payload.model_dump())
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/{submission_id}/reviews", response_model=list[ReviewOut])
def list_reviews(submission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Blind-review-style visibility: the organizer/co-admin/platform_admin sees all
    reviews; a reviewer sees only their own; the researcher sees none directly here
    (they get the final Decision instead, not raw reviewer comments)."""
    sub = _get_submission_or_404(submission_id, db)

    if _is_conference_organizer_or_admin(sub, user, db):
        return db.query(Review).filter(Review.submission_id == submission_id).all()

    if user.role == "reviewer":
        own = (
            db.query(Review)
            .filter(Review.submission_id == submission_id, Review.reviewer_id == user.id)
            .all()
        )
        return own

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")


@router.post("/{submission_id}/assign-reviewer", response_model=ReviewerAssignmentOut, status_code=status.HTTP_201_CREATED)
def assign_reviewer(
    submission_id: str,
    payload: AssignReviewerIn,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    """update51 — the organizer/co-admin allocates a SPECIFIC paper to a
    SPECIFIC reviewer. The reviewer must already be a pool member for this
    conference (ConferenceReviewer) — this assigns from that existing
    pool, it doesn't invite someone new to the conference."""
    sub = _get_submission_or_404(submission_id, db)
    if not _is_conference_organizer_or_admin(sub, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    is_pool_member = (
        db.query(ConferenceReviewer)
        .filter(
            ConferenceReviewer.conference_id == sub.conference_id,
            ConferenceReviewer.reviewer_id == payload.reviewer_id,
        )
        .first()
        is not None
    )
    if not is_pool_member:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That user is not in this conference's reviewer pool yet — invite them as a conference reviewer first.",
        )

    existing = (
        db.query(SubmissionReviewerAssignment)
        .filter(
            SubmissionReviewerAssignment.submission_id == submission_id,
            SubmissionReviewerAssignment.reviewer_id == payload.reviewer_id,
        )
        .first()
    )
    if existing:
        return existing

    assignment = SubmissionReviewerAssignment(
        submission_id=submission_id, reviewer_id=payload.reviewer_id, assigned_by=user.id
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.get("/{submission_id}/assigned-reviewers", response_model=list[ReviewerAssignmentOut])
def list_assigned_reviewers(
    submission_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = _get_submission_or_404(submission_id, db)
    if not _is_conference_organizer_or_admin(sub, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return db.query(SubmissionReviewerAssignment).filter(SubmissionReviewerAssignment.submission_id == submission_id).all()


@router.delete("/{submission_id}/assign-reviewer/{reviewer_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_reviewer(
    submission_id: str,
    reviewer_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    sub = _get_submission_or_404(submission_id, db)
    if not _is_conference_organizer_or_admin(sub, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    assignment = (
        db.query(SubmissionReviewerAssignment)
        .filter(
            SubmissionReviewerAssignment.submission_id == submission_id,
            SubmissionReviewerAssignment.reviewer_id == reviewer_id,
        )
        .first()
    )
    if assignment:
        db.delete(assignment)
        db.commit()
    return None


@router.post("/{submission_id}/decision", response_model=DecisionOut)
def make_decision(
    submission_id: str,
    payload: DecisionIn,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    sub = _get_submission_or_404(submission_id, db)
    if not _is_conference_organizer_or_admin(sub, user, db):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    existing = db.query(Decision).filter(Decision.submission_id == submission_id).first()
    if existing:
        existing.decision = payload.decision
        existing.notes = payload.notes
        existing.decided_by = user.id
    else:
        db.add(Decision(submission_id=submission_id, decided_by=user.id, **payload.model_dump()))

    status_map = {"accept": "accepted", "reject": "rejected", "revise_resubmit": "revise_resubmit"}
    sub.status = status_map[payload.decision]

    db.commit()
    result = db.query(Decision).filter(Decision.submission_id == submission_id).first()
    return result


@router.get("/{submission_id}/decision", response_model=DecisionOut)
def get_decision(submission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = _get_submission_or_404(submission_id, db)

    is_owner = sub.researcher_id == user.id
    if not (is_owner or _is_conference_organizer_or_admin(sub, user, db)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    decision = db.query(Decision).filter(Decision.submission_id == submission_id).first()
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No decision made yet")
    return decision
