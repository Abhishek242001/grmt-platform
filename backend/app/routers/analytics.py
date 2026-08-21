from collections import Counter
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.conferences import Conference, ConferenceCoAdmin
from app.models.core import User
from app.models.submissions import Decision, Review, Submission
from app.schemas.analytics import ConferenceAnalytics

router = APIRouter(prefix="/api/conferences", tags=["analytics"])


def _get_owned_conference_or_404(conference_id: str, user: User, db: Session) -> Conference:
    conf = db.query(Conference).filter(Conference.id == conference_id).first()
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")
    is_owner = conf.organizer_id == user.id
    is_admin = user.role == "platform_admin"
    is_coadmin = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == conference_id, ConferenceCoAdmin.user_id == user.id)
        .first() is not None
    )
    if not (is_owner or is_admin or is_coadmin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")
    return conf


@router.get("/{conference_id}/analytics", response_model=ConferenceAnalytics)
def get_analytics(
    conference_id: str,
    user: User = Depends(require_role("organizer", "platform_admin")),
    db: Session = Depends(get_db),
):
    _get_owned_conference_or_404(conference_id, user, db)

    submissions = db.query(Submission).filter(Submission.conference_id == conference_id).all()
    sub_ids = [s.id for s in submissions]

    status_counts = Counter(s.status for s in submissions)
    review_count = db.query(Review).filter(Review.submission_id.in_(sub_ids)).count() if sub_ids else 0
    decision_count = db.query(Decision).filter(Decision.submission_id.in_(sub_ids)).count() if sub_ids else 0

    return ConferenceAnalytics(
        conference_id=conference_id,
        total_submissions=len(submissions),
        submissions_by_status=dict(status_counts),
        total_reviews_submitted=review_count,
        total_decisions_made=decision_count,
        average_reviews_per_submission=round(review_count / len(submissions), 2) if submissions else 0.0,
    )
