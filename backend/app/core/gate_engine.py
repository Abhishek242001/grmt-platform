"""Gate Rule Engine — the business logic that decides whether an AI check
result should block a submission, flag it, or let it through. This is NOT an
AI model itself; it's deterministic rule evaluation applied to AI check
outputs (per the product's own distinction — planning log Discussion 6/§2).

Per-check evaluators are registered in CHECK_EVALUATORS. Each takes the
check's parsed result dict and the organizer's configured threshold, and
returns True if the submission PASSES that check (no flag).
"""
import json

from sqlalchemy.orm import Session

from app.models.conferences import GateRule
from app.models.submissions import AIReport, Submission


def _grammar_passes(result: dict, threshold: float | None) -> bool:
    if threshold is None:
        return True  # no threshold configured — informational only, never gates
    score = result.get("score")
    if score is None:
        return True  # the check itself errored; don't gate on a failed check
    return score >= threshold


def _format_passes(result: dict, threshold: float | None) -> bool:
    # Same shape as grammar's evaluator — format-compliance's score is also a
    # 0-100 scale (checks_passed / checks_total), so the comparison is identical.
    if threshold is None:
        return True
    score = result.get("score")
    if score is None:
        return True
    return score >= threshold


CHECK_EVALUATORS = {
    "grammar": _grammar_passes,
    "format": _format_passes,
    # citation, plagiarism, ai_text, table_figure, logical_consistency
    # register here as each check is built — this is the one place that needs
    # a new line added, not a rewrite of the evaluation logic itself.
}


def evaluate_submission_gates(submission_id: str, db: Session) -> str:
    """Evaluates only the checks that have actually COMPLETED for this
    submission — with 1 of 7 checks currently implemented, this deliberately
    never returns "ai_review_passed" (that would claim the full pipeline ran
    clean). It returns "ai_review_hard_failed" if any hard-gated check failed,
    otherwise "in_human_review" — nothing blocking found among what has run."""
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if sub is None:
        return "unknown"

    gate_rules = {
        r.check_type: r
        for r in db.query(GateRule).filter(GateRule.conference_id == sub.conference_id).all()
    }
    reports = (
        db.query(AIReport)
        .filter(AIReport.submission_id == submission_id, AIReport.status == "complete")
        .all()
    )

    hard_failed = False
    for report in reports:
        rule = gate_rules.get(report.check_type)
        if rule is None:
            continue  # organizer hasn't configured a gate rule for this check type

        evaluator = CHECK_EVALUATORS.get(report.check_type)
        if evaluator is None:
            continue  # no evaluator registered yet for this check type

        try:
            result = json.loads(report.result_json) if report.result_json else {}
        except (json.JSONDecodeError, TypeError):
            continue

        passed = evaluator(result, rule.threshold)
        if not passed and rule.is_hard_gate:
            hard_failed = True

    new_status = "ai_review_hard_failed" if hard_failed else "in_human_review"
    sub.status = new_status
    db.commit()
    return new_status
