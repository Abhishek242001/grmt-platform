import json
import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
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


def _convert_to_pdf_and_store(submission_id: str, version_id: str, file_path: str) -> None:
    """Runs before the AI checks, in the same background task, but kept as
    its own function/step: a conversion failure must never block grammar/
    format/table_figure checks from running against the original file —
    those don't depend on the PDF at all. Populates
    SubmissionVersion.converted_pdf_url, which already existed as a schema
    field from Phase 1 (built for the reviewer's PDF annotation viewer)
    but was never populated until this."""
    import asyncio

    from app.core.word_to_pdf import ConversionError, convert_to_pdf
    from app.core.ws_manager import get_manager

    db = database_module.SessionLocal()
    try:
        version = db.query(SubmissionVersion).filter(SubmissionVersion.id == version_id).first()
        if version is None:
            return
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if sub is None:
            return

        ext = os.path.splitext(file_path)[1].lower()
        converted = False
        error = None
        if ext == ".pdf":
            # Already a PDF — no conversion needed, just point at itself so
            # the frontend never has to branch on original file type.
            version.converted_pdf_url = file_path
            converted = True
        else:
            try:
                output_dir = os.path.dirname(file_path)
                pdf_path = convert_to_pdf(file_path, output_dir)
                version.converted_pdf_url = pdf_path
                converted = True
            except ConversionError as e:
                # Non-fatal: AI checks still run against the original file
                # regardless (see _run_ai_checks_and_store). The reviewer
                # PDF viewer just won't have a converted PDF to show for
                # this version until re-attempted.
                error = str(e)

        db.commit()

        asyncio.run(get_manager().publish(
            f"conference:{sub.conference_id}:queue",
            {
                "type": "submission_version.pdf_converted",
                "submission_id": submission_id,
                "version_id": version_id,
                "converted": converted,
                "error": error,
            },
        ))
        # Also to the per-submission channel — conference:queue is
        # organizer/co-admin only, but the submission detail page (where
        # this actually matters, for the PDF viewer) is viewed by the
        # researcher and assigned reviewers too. See ws.py's
        # _authorize_channel for the scoping.
        asyncio.run(get_manager().publish(
            f"submission:{submission_id}:updates",
            {
                "type": "submission_version.pdf_converted",
                "submission_id": submission_id,
                "version_id": version_id,
                "converted": converted,
                "error": error,
            },
        ))
    finally:
        db.close()


def _run_ai_checks_and_store(submission_id: str, version_id: str, file_path: str) -> None:
    """Runs in a worker thread via FastAPI's BackgroundTasks. Uses
    database_module.SessionLocal() (late-bound attribute access, not a name
    captured at import time) so conftest.py's test override actually reaches
    this code — see planning log §26 for why a direct import wouldn't work.

    Runs every check that's currently implemented (grammar, format,
    table_figure, ai_text) — new checks get added to this loop, not a new
    copy of this whole function."""
    import asyncio

    from app.ai.ai_content_pipeline import run_ai_text_detection_check
    from app.ai.format_compliance_check import run_format_compliance_check
    from app.ai.grammar_check import run_grammar_check
    from app.ai.table_figure_check import run_table_figure_check
    from app.core.gate_engine import evaluate_submission_gates
    from app.core.ws_manager import get_manager

    _convert_to_pdf_and_store(submission_id, version_id, file_path)

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
            ("table_figure", lambda: run_table_figure_check(file_path)),
            # Real GPU inference (followsci BERT model) — meaningfully
            # slower than the three checks above and needs torch/
            # transformers installed on whatever machine runs this
            # background task. Already gracefully degrades to a normal
            # {"status": "error", ...} result (not a crash) if torch/
            # transformers aren't installed or no GPU is available — see
            # ai_content_pipeline.run_pipeline's try/except around scoring.
            ("ai_text", lambda: run_ai_text_detection_check(file_path)),
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
            asyncio.run(get_manager().publish(
                f"submission:{submission_id}:updates",
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
        asyncio.run(get_manager().publish(
            f"submission:{submission_id}:updates",
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

    background_tasks.add_task(_run_ai_checks_and_store, submission_id, version.id, dest_path)

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


@router.post("/{submission_id}/resubmit", response_model=SubmissionVersionOut)
async def resubmit(
    submission_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    """Mirrors /upload's real-multipart pattern exactly — this used to
    accept JSON metadata + a placeholder URL (the same pre-upload shape
    /submissions originally had) and could never honestly claim
    "processing", since no background task would ever run to resolve
    that status. Real fix, not a workaround: real file bytes in, a real
    new SubmissionVersion, a real background task, a real "processing"
    status that a real check run will actually resolve."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None or sub.researcher_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    if sub.status != "revise_resubmit":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Submission is not in a resubmittable state (current status: {sub.status})",
        )

    ALLOWED_EXTENSIONS = (".docx", ".pdf")
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only .docx or .pdf files are accepted")

    latest = (
        db.query(SubmissionVersion)
        .filter(SubmissionVersion.submission_id == submission_id)
        .order_by(SubmissionVersion.version_number.desc())
        .first()
    )
    next_version = (latest.version_number + 1) if latest else 1

    version_dir = os.path.join(
        _BACKEND_DIR, settings.upload_root, "submissions", submission_id, f"v{next_version}"
    )
    os.makedirs(version_dir, exist_ok=True)
    dest_path = os.path.join(version_dir, file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    version = SubmissionVersion(
        submission_id=submission_id,
        version_number=next_version,
        original_filename=file.filename,
        original_file_url=dest_path,
    )
    db.add(version)

    if title:
        sub.title = title
    sub.status = "processing"  # honestly "processing" now — a real background task will resolve it
    db.commit()
    db.refresh(version)

    background_tasks.add_task(_run_ai_checks_and_store, submission_id, version.id, dest_path)

    from app.core.ws_manager import get_manager
    await get_manager().publish(
        f"conference:{sub.conference_id}:queue",
        {"type": "submission.resubmitted", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )
    await get_manager().publish(
        f"submission:{sub.id}:updates",
        {"type": "submission.resubmitted", "submission_id": sub.id, "title": sub.title, "status": sub.status},
    )

    return version
