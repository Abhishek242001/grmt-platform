from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.ai_checks import check_grammar, check_structure, extract_text_from_pdf
from app.core.database import get_db
from app.core.deps import get_current_user, get_request_id, require_role
from app.core.gate_engine import evaluate_gate_rules
from app.core.logging_utils import log
from app.core.storage import generate_signed_url_token, save_file
from app.models.core import Conference, GateRule, User
from app.models.submissions import AIReport, Submission, SubmissionVersion

router = APIRouter(prefix="/submissions", tags=["submissions"])

# ai_reports.check_type -> gate_rules.rule_type. Not every check_type has a
# corresponding configurable gate yet (grammar has no gate_rules entry in
# this build — see scripts/seed_demo_data.py) — only mapped check types
# participate in the hard/soft gate decision below. Extend this mapping as
# more checks (plagiarism, ai_text, table_figure) get wired in later phases.
CHECK_TYPE_TO_RULE_TYPE = {
    "citation": "citation_completeness",
}


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
    master doc §5.3 / §2.3's request flow. This build runs the grammar
    (LanguageTool) and citation/structure (GROBID) checks synchronously,
    in-request — the two CPU-only, Docker-based checks per master doc §3.1/
    §3.2 (Phase 2, Days 6-7 scope). Plagiarism/AI-text/LLM checks are NOT
    dispatched here — those need the GPU services (Phase 3, §3.3/§3.5/§3.6)
    and remain future work; §2.3's background-task/async design is the
    right shape once those longer-running GPU checks are added, but a
    synchronous call is a reasonable, honest starting point for two
    checks that each complete in seconds against a Docker service already
    running locally.
    """
    req_id = get_request_id(request)
    conference = db.query(Conference).filter(Conference.id == conference_id).first()
    if conference is None:
        raise HTTPException(status_code=404, detail="Conference not found")

    content = file.file.read()

    submission = Submission(researcher_id=user.id, conference_id=conference_id, title=title, abstract=abstract, track=track, status="processing")
    db.add(submission)
    db.flush()

    storage_key, file_hash = save_file(submission.id, version_number=1, filename=file.filename or "submission.pdf", content=content)

    version = SubmissionVersion(
        submission_id=submission.id,
        version_number=1,
        file_url=storage_key,
        file_hash=file_hash,
    )
    db.add(version)
    db.flush()
    submission.current_version_id = version.id
    db.commit()
    db.refresh(submission)

    log.info(req_id, f"submission created id={submission.id} conference={conference_id} researcher={user.id}")

    _run_ai_checks_and_gate(db, req_id, submission, version, content, conference_id)

    db.refresh(submission)
    return {"id": submission.id, "status": submission.status, "current_version_id": version.id, "conference_id": conference_id}


def _run_ai_checks_and_gate(db: Session, req_id: str, submission: Submission, version: SubmissionVersion, pdf_bytes: bytes, conference_id: str) -> None:
    """
    Runs the wired checks, writes one ai_reports row per check (master doc
    §4.3), then evaluates the conference's gate rules against the results
    and updates submission.status accordingly (master doc §2.5/Figure 2).

    Each check is wrapped so one check's failure (e.g. GROBID unreachable)
    doesn't take down the whole submission — it's logged and the submission
    proceeds with whatever checks did succeed, rather than the researcher
    getting a bare 500 for an infrastructure problem that isn't their fault.
    """
    report_for_gate: dict[str, dict] = {}

    try:
        text = extract_text_from_pdf(pdf_bytes)
        grammar_result = check_grammar(text)
        _write_ai_report(db, version.id, grammar_result)
        log.info(req_id, f"grammar check complete submission={submission.id} score={grammar_result['score']}")
    except Exception as e:
        log.error(req_id, f"grammar check failed submission={submission.id}: {e}", exc=e)

    try:
        structure_result = check_structure(pdf_bytes)
        _write_ai_report(db, version.id, structure_result)
        rule_type = CHECK_TYPE_TO_RULE_TYPE.get(structure_result["check_type"])
        if rule_type:
            report_for_gate[rule_type] = {"score": structure_result["score"], "pass_fail": structure_result["pass_fail"]}
        log.info(req_id, f"structure/citation check complete submission={submission.id} score={structure_result['score']}")
    except Exception as e:
        log.error(req_id, f"structure/citation check failed submission={submission.id}: {e}", exc=e)

    gate_rules = db.query(GateRule).filter(GateRule.conference_id == conference_id).all()
    rules_as_dicts = [
        {"rule_type": r.rule_type, "threshold_soft": float(r.threshold_soft) if r.threshold_soft is not None else None,
         "threshold_hard": float(r.threshold_hard) if r.threshold_hard is not None else None, "is_hard_gate": r.is_hard_gate}
        for r in gate_rules
    ]
    decision = evaluate_gate_rules(rules_as_dicts, report_for_gate)

    if decision.hard_fail:
        submission.status = "ai_review_hard_failed"
    else:
        submission.status = "ai_review_passed"
    db.commit()

    log.info(
        req_id,
        f"gate decision submission={submission.id} status={submission.status} "
        f"hard_fail_reasons={decision.hard_fail_reasons} soft_flags={decision.soft_flags}",
    )


def _write_ai_report(db: Session, version_id: str, result: dict) -> None:
    report = AIReport(
        submission_version_id=version_id,
        check_type=result["check_type"],
        result_json=result["result_json"],
        score=result["score"],
        pass_fail=result["pass_fail"],
        flagged=result["flagged"],
        model_version=result["model_version"],
    )
    db.add(report)
    db.commit()


@router.get("/{submission_id}")
def get_submission(submission_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
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


@router.get("/{submission_id}/file-url")
def get_file_url(submission_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    development_rule.md §6.4 — issues a short-lived signed URL for the
    current version's file rather than exposing the raw storage path. Call
    this each time the PDF viewer needs to (re)load the file; do not cache
    the returned URL beyond its expires_at.
    """
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    if user.role == "researcher" and sub.researcher_id != user.id:
        raise HTTPException(status_code=404, detail="Submission not found")

    version = db.query(SubmissionVersion).filter(SubmissionVersion.id == sub.current_version_id).first()
    if version is None:
        raise HTTPException(status_code=404, detail="No file for this submission")

    token, expires_at = generate_signed_url_token(version.file_url)
    return {"url": f"/api/files/{token}", "expires_at": expires_at}
