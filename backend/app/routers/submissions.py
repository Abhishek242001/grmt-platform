import json
import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core import database as database_module
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
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

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


def _run_ai_checks_and_store(submission_id: str, file_path: str) -> None:
    """Runs in a worker thread via FastAPI's BackgroundTasks. Uses
    database_module.SessionLocal() (late-bound attribute access, not a name
    captured at import time) so conftest.py's test override actually reaches
    this code — see planning log §26 for why a direct import wouldn't work.

    Runs every check that's currently implemented (grammar, format) — new
    checks get added to this loop, not a new copy of this whole function."""
    import asyncio

    from app.ai.format_compliance_check import run_format_compliance_check
    from app.ai.grammar_check import run_grammar_check
    from app.core.gate_engine import evaluate_submission_gates
    from app.core.ws_manager import get_manager

    db = database_module.SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if sub is None:
            return
        conf = db.query(Conference).filter(Conference.id == sub.conference_id).first()
        publisher_format = conf.publisher_format if conf else "ieee"

        checks_to_run = [
            ("grammar", lambda: run_grammar_check(file_path)),
            ("format", lambda: run_format_compliance_check(file_path, publisher_format=publisher_format)),
        ]

        for check_type, run_fn in checks_to_run:
            result = run_fn()
            report = AIReport(
                submission_id=submission_id,
                check_type=check_type,
                status="complete" if result.get("status") == "complete" else "error",
                result_json=json.dumps(result),
            )
            db.add(report)
            db.commit()

            asyncio.run(get_manager().publish(
                f"conference:{sub.conference_id}:queue",
                {
                    "type": "ai_report.check_completed",
                    "submission_id": submission_id,
                    "check_type": check_type,
                    "check_status": report.status,
                },
            ))

        new_status = evaluate_submission_gates(submission_id, db)
        asyncio.run(get_manager().publish(
            f"conference:{sub.conference_id}:queue",
            {"type": "submission.status_changed", "submission_id": submission_id, "submission_status": new_status},
        ))
    finally:
        db.close()


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

    from app.core.ws_manager import get_manager
    await get_manager().publish(
        f"conference:{payload.conference_id}:queue",
        {"type": "submission.created", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )

    return sub


@router.post("/{submission_id}/upload", response_model=SubmissionVersionOut)
async def upload_file(
    submission_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None or sub.researcher_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    ALLOWED_EXTENSIONS = (".docx", ".pdf")
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .docx or .pdf files are accepted")

    version = (
        db.query(SubmissionVersion)
        .filter(SubmissionVersion.submission_id == submission_id)
        .order_by(SubmissionVersion.version_number.desc())
        .first()
    )
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No version record found for this submission")

    version_dir = os.path.join(
        _BACKEND_DIR, settings.upload_root, "submissions", submission_id, f"v{version.version_number}"
    )
    os.makedirs(version_dir, exist_ok=True)
    dest_path = os.path.join(version_dir, file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    version.original_file_url = dest_path
    db.commit()
    db.refresh(version)

    sub.status = "processing"
    db.commit()

    background_tasks.add_task(_run_ai_checks_and_store, submission_id, dest_path)

    return version


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
    # Stays "submitted", not "processing" — this endpoint doesn't accept real
    # file bytes yet (JSON metadata + a placeholder URL, the same pre-upload
    # shape /submissions originally had), so no check actually runs here.
    # Claiming "processing" without a background task to ever resolve it
    # would recreate the exact stuck-forever bug the real /upload flow fixed
    # (planning log §26) — this is a documented gap, not silently dropped:
    # resubmit needs the same real-multipart-upload treatment as /upload,
    # as a follow-up, before this can honestly say "processing".
    sub.status = "submitted"
    db.commit()
    db.refresh(sub)

    from app.core.ws_manager import get_manager
    await get_manager().publish(
        f"conference:{sub.conference_id}:queue",
        {"type": "submission.resubmitted", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )

    return sub
