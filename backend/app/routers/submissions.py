from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.ws_manager import get_manager
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer
from app.models.core import User
from app.models.submissions import AIReport, Submission, SubmissionVersion
from app.schemas.submissions import (
    AIReportOut,
    ResubmitRequest,
    SubmissionCreate,
    SubmissionOut,
    SubmissionVersionOut,
)

router = APIRouter(prefix="/api/submissions", tags=["submissions"])


def _get_visible_submission_or_404(submission_id: str, user: User, db: Session) -> Submission:
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if sub.researcher_id == user.id or user.role == "platform_admin":
        return sub

    conf = db.query(Conference).filter(Conference.id == sub.conference_id).first()
    if conf and conf.organizer_id == user.id:
        return sub

    is_coadmin = (
        db.query(ConferenceCoAdmin)
        .filter(ConferenceCoAdmin.conference_id == sub.conference_id, ConferenceCoAdmin.user_id == user.id)
        .first() is not None
    )
    is_reviewer = (
        db.query(ConferenceReviewer)
        .filter(ConferenceReviewer.conference_id == sub.conference_id, ConferenceReviewer.reviewer_id == user.id)
        .first() is not None
    )
    if is_coadmin or is_reviewer:
        return sub

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def create_submission(
    payload: SubmissionCreate,
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    conf = db.query(Conference).filter(Conference.id == payload.conference_id).first()
    if conf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conference not found")

    sub = Submission(conference_id=payload.conference_id, researcher_id=user.id, title=payload.title)
    db.add(sub)
    db.flush()

    version = SubmissionVersion(
        submission_id=sub.id,
        version_number=1,
        original_filename=payload.original_filename,
        original_file_url=payload.original_file_url,
    )
    db.add(version)
    db.commit()
    db.refresh(sub)

    # Live-push to any organizer/co-admin/platform_admin currently watching this
    # conference's queue. No-op (returns 0) if nobody's subscribed — that's fine,
    # this isn't the only way to see submissions, just the live-update path.
    await get_manager().publish(
        f"conference:{payload.conference_id}:queue",
        {"type": "submission.created", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )

    return sub


@router.get("/mine", response_model=list[SubmissionOut])
def my_submissions(user: User = Depends(require_role("researcher")), db: Session = Depends(get_db)):
    return db.query(Submission).filter(Submission.researcher_id == user.id).all()


@router.get("/assigned", response_model=list[SubmissionOut])
def assigned_submissions(user: User = Depends(require_role("reviewer")), db: Session = Depends(get_db)):
    conf_ids = [
        row.conference_id
        for row in db.query(ConferenceReviewer).filter(ConferenceReviewer.reviewer_id == user.id).all()
    ]
    if not conf_ids:
        return []
    return db.query(Submission).filter(Submission.conference_id.in_(conf_ids)).all()


@router.get("/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_visible_submission_or_404(submission_id, user, db)


@router.get("/{submission_id}/ai-report", response_model=list[AIReportOut])
def get_ai_report(submission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_visible_submission_or_404(submission_id, user, db)
    return db.query(AIReport).filter(AIReport.submission_id == submission_id).all()


@router.get("/{submission_id}/history", response_model=list[SubmissionVersionOut])
def get_submission_history(submission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _get_visible_submission_or_404(submission_id, user, db)
    return (
        db.query(SubmissionVersion)
        .filter(SubmissionVersion.submission_id == submission_id)
        .order_by(SubmissionVersion.version_number)
        .all()
    )


@router.post("/{submission_id}/resubmit", response_model=SubmissionOut)
async def resubmit(
    submission_id: str,
    payload: ResubmitRequest,
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None or sub.researcher_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    if sub.status != "revise_resubmit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not in a resubmittable state (current status: {sub.status})",
        )

    latest = (
        db.query(SubmissionVersion)
        .filter(SubmissionVersion.submission_id == submission_id)
        .order_by(SubmissionVersion.version_number.desc())
        .first()
    )
    next_version = (latest.version_number + 1) if latest else 1

    db.add(SubmissionVersion(
        submission_id=submission_id,
        version_number=next_version,
        original_filename=payload.original_filename,
        original_file_url=payload.original_file_url,
    ))
    if payload.title:
        sub.title = payload.title
    sub.status = "submitted"
    db.commit()
    db.refresh(sub)

    await get_manager().publish(
        f"conference:{sub.conference_id}:queue",
        {"type": "submission.resubmitted", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )

    return sub
