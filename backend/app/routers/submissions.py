import json
import os
import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core import database as database_module
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.logging_utils import get_logger
from app.models.conferences import Conference, ConferenceCoAdmin, ConferenceReviewer
from app.models.core import User
from app.models.submissions import (
    AIReport,
    Decision,
    Submission,
    SubmissionReviewerAssignment,
    SubmissionVersion,
)
from app.schemas.submissions import (
    AIReportOut,
    ResubmitRequest,
    SubmissionCreate,
    SubmissionOut,
    SubmissionVersionOut,
)

router = APIRouter(prefix="/api/submissions", tags=["submissions"])
logger = get_logger("grmt.submissions")

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
        and db.query(SubmissionReviewerAssignment)
        .filter(SubmissionReviewerAssignment.submission_id == sub.id, SubmissionReviewerAssignment.reviewer_id == user.id)
        .first() is not None
    )
    # update51 — a reviewer must now be BOTH a pool member for this
    # conference AND specifically assigned to THIS paper. Before this
    # change, any pool member could see (and review) every submission in
    # the conference — see SubmissionReviewerAssignment's docstring.
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
        # Returned so _run_ai_checks_and_store can hand the real converted
        # PDF path to the citation check (GROBID needs a PDF specifically —
        # see citation_check.py) without querying the DB a second time.
        return version.converted_pdf_url if converted else None
    finally:
        db.close()


def _fetch_plagiarism_candidates(db, current_submission_id: str) -> list[dict]:
    """Fetches {"submission_id", "text"} for every OTHER submission's latest
    version, re-extracting text on demand from each candidate's original
    file (phase 1 of 3 — see plagiarism_scoring.py's docstring for the full
    corpus-decision context).

    Honest, real limitation, not hidden: this re-reads and re-parses every
    OTHER submission's file on every single plagiarism check — it doesn't
    scale indefinitely. Fine for a reasonable submission count; a genuine
    future optimization would persist extracted text (or embeddings) once
    per version instead of re-extracting it on every comparison. Left as a
    documented follow-up, not solved here, since it's a real infrastructure
    decision (where does that get stored, invalidated on resubmit, etc.),
    not a small addition to this function.

    A candidate whose file can't be read (missing, corrupt, unsupported
    type) is silently skipped rather than failing the whole check — one
    bad prior submission shouldn't block checking a new one."""
    from app.ai.grammar_check import extract_text

    other_submissions = db.query(Submission).filter(Submission.id != current_submission_id).all()

    candidates = []
    for sub in other_submissions:
        latest_version = (
            db.query(SubmissionVersion)
            .filter(SubmissionVersion.submission_id == sub.id)
            .order_by(SubmissionVersion.version_number.desc())
            .first()
        )
        if latest_version is None:
            continue
        try:
            text, _ = extract_text(latest_version.original_file_url)
        except Exception:
            continue
        if text.strip():
            candidates.append({"submission_id": sub.id, "text": text})

    return candidates


def _build_external_plagiarism_check_fn(db):
    """Builds the callable passed as plagiarism_check.py's external_check_fn
    (update45) — or returns None if no provider is currently active, so the
    caller can skip external comparison entirely rather than pass a
    guaranteed-to-no-op closure.

    This is where the admin panel's stored, encrypted API key actually gets
    used for the first time — everything built in update44 (ApiProviderConfig,
    key_encryption.py) was infrastructure; this is the piece that spends it.
    Also responsible for logging every real call to ApiUsageLog, success or
    failure, which is what the admin panel's usage dashboard reads.

    update49: logs every decision point explicitly — whether an active
    provider was found at all, which one, and the real outcome of the call
    — so a "why didn't this call anything" question can be answered by
    reading backend.log instead of guessing."""
    from app.core.key_encryption import decrypt_api_key
    from app.models.admin import ApiProviderConfig, ApiUsageLog

    active = db.query(ApiProviderConfig).filter(ApiProviderConfig.is_active == True).first()  # noqa: E712
    if active is None:
        logger.info("plagiarism external check: no ApiProviderConfig row is currently active — skipping")
        return None
    if active.encrypted_key is None:
        logger.info("plagiarism external check: provider %r is active but has no key configured — skipping", active.provider)
        return None

    provider = active.provider
    logger.info("plagiarism external check: provider %r is active, building real check callable", provider)

    try:
        api_key = decrypt_api_key(active.encrypted_key)
    except Exception:
        logger.exception("plagiarism external check: failed to decrypt stored key for provider %r — skipping", provider)
        return None

    def _check(text: str) -> dict:
        logger.info("plagiarism external check: calling provider %r with %d characters of text", provider, len(text))

        if provider == "winston":
            from app.ai.winston_plagiarism_client import run_winston_plagiarism_check

            result = run_winston_plagiarism_check(api_key, text)
        elif provider == "gptzero":
            # GPTZero's API requires a paid plan (confirmed — its free tier
            # is web-app-only, no API access at all) — not wired up yet
            # since this project is currently using Winston AI's free tier
            # instead. Activating "gptzero" in the admin panel with a real
            # key would still need a client module built for it, matching
            # winston_plagiarism_client.py's pattern, once there's budget.
            result = {"status": "error", "error": f"No client implemented yet for provider {provider!r}"}
        else:
            result = {"status": "error", "error": f"Unknown provider {provider!r}"}

        logger.info(
            "plagiarism external check: provider %r returned status=%r (error=%r)",
            provider, result.get("status"), result.get("error"),
        )

        log = ApiUsageLog(
            provider=provider,
            purpose="plagiarism_check",
            success=result.get("status") == "complete",
            response_time_ms=result.get("response_time_ms"),
            error_message=result.get("error") if result.get("status") != "complete" else None,
        )
        db.add(log)
        db.commit()

        return result

    return _check


def _run_ai_checks_and_store(submission_id: str, version_id: str, file_path: str) -> None:
    """Runs in a worker thread via FastAPI's BackgroundTasks. Uses
    database_module.SessionLocal() (late-bound attribute access, not a name
    captured at import time) so conftest.py's test override actually reaches
    this code — see planning log §26 for why a direct import wouldn't work.

    Runs every check that's currently implemented (grammar, format,
    table_figure, ai_text, citation, logical_consistency) — new checks get
    added to this loop, not a new copy of this whole function."""
    import asyncio

    from app.ai.ai_content_pipeline import run_ai_text_detection_check
    from app.ai.citation_check import run_citation_check
    from app.ai.format_compliance_check import run_format_compliance_check
    from app.ai.grammar_check import run_grammar_check
    from app.ai.logical_consistency_check import run_logical_consistency_check
    from app.ai.plagiarism_check import run_plagiarism_check
    from app.ai.table_figure_check import run_table_figure_check
    from app.core.gate_engine import evaluate_submission_gates
    from app.core.ws_manager import get_manager

    converted_pdf_path = _convert_to_pdf_and_store(submission_id, version_id, file_path)

    db = database_module.SessionLocal()
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if sub is None:
            return
        conf = db.query(Conference).filter(Conference.id == sub.conference_id).first()
        publisher_format = conf.publisher_format if conf else "ieee"

        checks_to_run = [
            ("grammar", lambda: run_grammar_check(file_path)),
            (
                "format",
                lambda: run_format_compliance_check(
                    file_path, publisher_format=publisher_format, converted_pdf_path=converted_pdf_path
                ),
            ),
            ("table_figure", lambda: run_table_figure_check(file_path)),
            # Real GPU inference (followsci BERT model) — meaningfully
            # slower than the three checks above and needs torch/
            # transformers installed on whatever machine runs this
            # background task. Already gracefully degrades to a normal
            # {"status": "error", ...} result (not a crash) if torch/
            # transformers aren't installed or no GPU is available — see
            # ai_content_pipeline.run_pipeline's try/except around scoring.
            (
                "ai_text",
                lambda: run_ai_text_detection_check(file_path, pdf_path_for_highlighting=converted_pdf_path or file_path),
            ),
            # GROBID needs a real PDF specifically — uses the converted
            # path from _convert_to_pdf_and_store above (works for both
            # .docx submissions, once converted, and .pdf submissions,
            # which point at themselves). If conversion failed or hasn't
            # completed, converted_pdf_path is None and citation_check.py
            # returns a clear "no PDF available" error rather than crashing.
            ("citation", lambda: run_citation_check(converted_pdf_path or file_path)),
            # First genuinely LLM-judgment check (Ollama + Qwen2.5-7B) —
            # needs Ollama running and a real GPU; gracefully degrades to
            # {"status": "error", ...} if unreachable, same pattern as
            # ai_text. Can never hard-gate regardless of result — see
            # gate_engine.py's _logical_consistency_passes and
            # models/conferences.py's NEVER_HARD_GATE.
            ("logical_consistency", lambda: run_logical_consistency_check(file_path)),
            # Plagiarism — self-submission always runs (phase 1, update43,
            # free, no external dependency). External-literature comparison
            # (phase 2, update45) runs too, IF an admin has configured and
            # activated a provider via the admin panel — _build_external_
            # plagiarism_check_fn returns None otherwise, and
            # plagiarism_check.py's external_check_fn=None skips it
            # entirely. Also NEVER_HARD_GATE — an automated similarity
            # score is informational for reviewers, never grounds for
            # auto-rejection on its own.
            (
                "plagiarism",
                lambda: run_plagiarism_check(
                    file_path,
                    candidates=_fetch_plagiarism_candidates(db, submission_id),
                    external_check_fn=_build_external_plagiarism_check_fn(db),
                ),
            ),
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

    sub = Submission(
        conference_id=payload.conference_id,
        researcher_id=user.id,
        title=payload.title,
        previously_rejected_disclosure=payload.previously_rejected_disclosure,
    )
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


@router.post("/{submission_id}/submit-for-review", response_model=SubmissionOut)
def submit_for_review(
    submission_id: str,
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    """update51 — the researcher-facing checkpoint the whole gate system
    was missing: AI checks running clean (status "ai_review_passed") no
    longer auto-advances to "in_human_review" on its own. The researcher
    must review the results themselves and explicitly call this endpoint.
    A hard-gate failure can never reach here successfully — the researcher
    must revise (resubmit a new version, which re-runs checks) and try
    again, exactly as requested: "he cannot submit his paper... he can
    again do some changes, then he can again apply."."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    if sub.researcher_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if sub.status == "ai_review_hard_failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This submission failed one or more required checks and cannot be sent for review. "
                "Revise your paper and upload a new version to try again."
            ),
        )
    if sub.status != "ai_review_passed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This submission isn't ready to send for review yet (current status: {sub.status}).",
        )

    sub.status = "in_human_review"
    db.commit()
    db.refresh(sub)

    import asyncio

    from app.core.ws_manager import get_manager
    asyncio.run(get_manager().publish(
        f"conference:{sub.conference_id}:queue",
        {"type": "submission.status_changed", "submission_id": submission_id, "submission_status": sub.status},
    ))
    asyncio.run(get_manager().publish(
        f"submission:{submission_id}:updates",
        {"type": "submission.status_changed", "submission_id": submission_id, "submission_status": sub.status},
    ))

    return sub


@router.post("/{submission_id}/camera-ready", response_model=SubmissionOut)
async def submit_camera_ready(
    submission_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    copyright_transfer_file: UploadFile = File(None),
    user: User = Depends(require_role("researcher")),
    db: Session = Depends(get_db),
):
    """update51/52 — only reachable once Decision.decision == "accept" for
    this paper (any acceptance — organizer's final decision, not the
    per-reviewer recommendation). copyright_transfer_file is genuinely
    optional per the product decision — its absence is not an error.

    update52 — the camera-ready file is now stored as a real new
    SubmissionVersion (same pattern as /resubmit), not just a bare path on
    Submission. This is the actual fix for a real reported gap: the main
    paper viewer always shows the LATEST version (history[-1] on the
    frontend, ordered by version_number) — before this change, camera-ready
    was invisible to that viewer entirely, so accepting a paper and
    uploading its camera-ready version left the organizer still looking at
    the original submitted draft with no way to see the real final one.
    Making camera-ready a real version means it naturally becomes "the
    latest version" and the existing viewer shows it with no frontend
    changes needed. Deliberately does NOT schedule _run_ai_checks_and_store
    — camera-ready is post-acceptance, re-running grammar/citation/etc.
    checks on it serves no purpose. It DOES reuse _convert_to_pdf_and_store
    on its own (self-contained, doesn't depend on the checks pipeline) so
    a .docx camera-ready file is still viewable as a PDF."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None or sub.researcher_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    decision = db.query(Decision).filter(Decision.submission_id == submission_id).first()
    if decision is None or decision.decision != "accept":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera-ready submission is only available once this paper has been accepted.",
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

    camera_ready_dir = os.path.join(_BACKEND_DIR, settings.upload_root, "submissions", submission_id, "camera-ready")
    os.makedirs(camera_ready_dir, exist_ok=True)

    dest_path = os.path.join(camera_ready_dir, file.filename)
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    version = SubmissionVersion(
        submission_id=submission_id,
        version_number=next_version,
        original_filename=file.filename,
        original_file_url=dest_path,
    )
    db.add(version)

    sub.camera_ready_file_url = dest_path

    if copyright_transfer_file is not None and copyright_transfer_file.filename:
        copyright_dest = os.path.join(camera_ready_dir, copyright_transfer_file.filename)
        with open(copyright_dest, "wb") as f:
            shutil.copyfileobj(copyright_transfer_file.file, f)
        sub.copyright_transfer_file_url = copyright_dest

    from datetime import datetime, timezone
    sub.camera_ready_uploaded_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sub)
    db.refresh(version)

    background_tasks.add_task(_convert_to_pdf_and_store, submission_id, version.id, dest_path)

    return sub


@router.get("/assigned", response_model=list[SubmissionOut])
def assigned_submissions(user: User = Depends(require_role("reviewer")), db: Session = Depends(get_db)):
    """update51 — now returns only papers actually assigned to this
    specific reviewer (SubmissionReviewerAssignment), not every submission
    in every conference where they're merely a pool member. The name was
    already "assigned" before this fix; the behavior now matches it."""
    submission_ids = [
        row.submission_id
        for row in db.query(SubmissionReviewerAssignment)
        .filter(SubmissionReviewerAssignment.reviewer_id == user.id)
        .all()
    ]
    if not submission_ids:
        return []
    return db.query(Submission).filter(Submission.id.in_(submission_ids)).all()


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
    if sub.status not in ("revise_resubmit", "ai_review_hard_failed"):
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
