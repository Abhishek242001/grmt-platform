import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_request_id, require_role
from app.core.logging_utils import log
from app.models.core import User
from app.models.submissions import AIReport, Submission, SubmissionVersion

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("", status_code=201)
def create_submission(
    request: Request,
    conference_id: str = Form(...),
    title: str = Form(...),
    abstract: str = Form(""),
    track: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("researcher")),
):
    """
    Master doc §5.3. In this starter codebase the file is hashed and a
    placeholder file_url is stored rather than actually uploading to
    Supabase/R2 — wire real storage per master doc §2.2.5 /
    development_rule.md §6.4 (signed URLs, no direct download links) before
    this goes anywhere beyond local dev. AI checks are NOT dispatched here
    yet — that's the AI Orchestration Service described in master doc §2.3,
    which calls the services scaffolded in ai-services/ once they're deployed
    to a Lightning Studio (development_rule.md §1).
    """
    req_id = get_request_id(request)
    content = file.file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    submission = Submission(researcher_id=user.id, conference_id=conference_id, title=title, abstract=abstract, track=track, status="processing")
    db.add(submission)
    db.flush()

    version = SubmissionVersion(
        submission_id=submission.id,
        version_number=1,
        file_url=f"placeholder://uploads/{submission.id}/v1/{file.filename}",
        file_hash=file_hash,
    )
    db.add(version)
    db.flush()
    submission.current_version_id = version.id
    db.commit()
    db.refresh(submission)

    log.info(req_id, f"submission created id={submission.id} conference={conference_id} researcher={user.id}")
    return {"id": submission.id, "status": submission.status, "current_version_id": version.id, "conference_id": conference_id}


@router.get("/{submission_id}")
def get_submission(submission_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        # 404 rather than 403 even for an access-denied case, per master doc §5.10 —
        # don't confirm existence of a resource the caller shouldn't see.
        raise HTTPException(status_code=404, detail="Submission not found")
    if user.role == "researcher" and sub.researcher_id != user.id:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {
        "id": sub.id,
        "title": sub.title,
        "status": sub.status,
        "conference_id": sub.conference_id,
        "current_version_id": sub.current_version_id,
    }


@router.get("/{submission_id}/ai-report")
def get_ai_report(submission_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    reports = (
        db.query(AIReport)
        .filter(AIReport.submission_version_id == sub.current_version_id)
        .all()
    )
    checks = [
        {
            "check_type": r.check_type,
            "score": float(r.score) if r.score is not None else None,
            "flagged": r.flagged,
            "pass_fail": r.pass_fail,
            "detail": r.result_json,
        }
        for r in reports
    ]
    return {"submission_id": sub.id, "version_id": sub.current_version_id, "overall_status": sub.status, "checks": checks}
