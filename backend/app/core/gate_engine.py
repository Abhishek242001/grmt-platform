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


def _table_figure_passes(result: dict, threshold: float | None) -> bool:
    # Same checks_passed/checks_total -> 0-100 score shape as format-
    # compliance, so the same comparison logic applies unchanged. A None
    # score here means the document had no tables/figures to check at all
    # (not a failure) — don't gate on that.
    if threshold is None:
        return True
    score = result.get("score")
    if score is None:
        return True
    return score >= threshold


def _ai_text_passes(result: dict, threshold: float | None) -> bool:
    # INVERTED comparison direction from every other evaluator above —
    # ai_content_pipeline.py's own module docstring flags this explicitly.
    # Grammar/format/table_figure all pass when score >= threshold (higher
    # is better — more checks passed, higher quality). This one passes
    # when the AI-generated percentage is BELOW the organizer's configured
    # maximum (lower is better — less AI-generated content). Copying the
    # >= pattern from the evaluators above would silently accept every
    # submission except one that's 100% AI-generated.
    #
    # Deliberately recomputes pass/fail from the raw ai_generated_percentage
    # against THIS call's threshold, rather than trusting result's own
    # "overall_verdict" field — that field was computed using whatever
    # default threshold was in effect when the check itself ran, which can
    # predate or differ from the organizer's actual GateRule.threshold
    # (e.g. if the organizer changes the gate rule after the check already
    # ran). This function is the single source of truth for the real gate
    # decision; the check's own "overall_verdict" is informational only.
    #
    # NOTE: this evaluator's return value can never actually trigger a hard
    # fail in practice — models/conferences.py's NEVER_HARD_GATE = {
    # "plagiarism", "ai_text"} is a DB-enforced constraint (ck_gate_rule_
    # never_hard_gate) that a GateRule for this check_type can never have
    # is_hard_gate=True in the first place. A deliberate safety decision
    # given the real false-positive risk found calibrating this check (see
    # PROJECT_HANDOFF.md's decision record) — a submission must never be
    # auto-rejected purely on an AI-detection score with no human review.
    # The evaluator still computes a real pass/fail (surfaced to reviewers
    # as a flag), it just can never escalate to an automatic hard failure.
    if threshold is None:
        return True
    percentage = result.get("ai_generated_percentage")
    if percentage is None:
        return True  # the check itself errored; don't gate on a failed check
    return percentage < threshold


def _citation_passes(result: dict, threshold: float | None) -> bool:
    # Same score >= threshold shape as format/table_figure — citation
    # completeness (broken references specifically; uncited references
    # deliberately don't affect score, see citation_check.py) is a
    # deterministic fact about the document, same category as those two
    # checks, so it CAN hard-gate — unlike ai_text/logical_consistency
    # below, this isn't an AI-judgment call with false-positive risk.
    if threshold is None:
        return True
    score = result.get("score")
    if score is None:
        return True
    return score >= threshold


def _logical_consistency_passes(result: dict, threshold: float | None) -> bool:
    # score >= threshold, same direction as grammar/format/table_figure/
    # citation (100 = consistent passes, 0 = inconsistent fails — NOT
    # inverted the way ai_text is). But like ai_text, this can never
    # actually trigger a hard fail in practice: models/conferences.py's
    # NEVER_HARD_GATE now includes "logical_consistency" alongside
    # "plagiarism"/"ai_text" — this is the first check that's a genuine
    # LLM *judgment* call (Ollama + Qwen2.5-7B reasoning about whether the
    # abstract and conclusion contradict each other) rather than
    # deterministic extraction, and it's genuinely unverified against a
    # real running Ollama service (see PROJECT_HANDOFF.md) — an unverified
    # AI judgment must not be able to auto-reject a submission any more
    # than ai_text's real, confirmed bias risk was allowed to.
    if threshold is None:
        return True
    score = result.get("score")
    if score is None:
        return True
    return score >= threshold


def _plagiarism_passes(result: dict, threshold: float | None) -> bool:
    # score >= threshold, same direction as grammar/format/table_figure/
    # citation/logical_consistency — plagiarism_check.py deliberately
    # computes score as (1 - highest_similarity) * 100, so higher score
    # already means LESS similarity/LESS concerning (100 = no overlap
    # found), matching this file's dominant convention rather than
    # ai_text's inverted one. Like ai_text/logical_consistency, this can
    # never actually trigger a hard fail in practice — models/
    # conferences.py's NEVER_HARD_GATE includes "plagiarism": an automated
    # TF-IDF similarity score is informational for reviewers (shared
    # domain terminology between two unrelated papers, permitted
    # self-citation, and genuine misconduct can all produce a flagged
    # score — a human must interpret what the similarity actually means),
    # never grounds for auto-rejection on its own.
    if threshold is None:
        return True
    score = result.get("score")
    if score is None:
        return True
    return score >= threshold


CHECK_EVALUATORS = {
    "grammar": _grammar_passes,
    "format": _format_passes,
    "table_figure": _table_figure_passes,
    "ai_text": _ai_text_passes,
    "citation": _citation_passes,
    "logical_consistency": _logical_consistency_passes,
    "plagiarism": _plagiarism_passes,
}


def evaluate_submission_gates(submission_id: str, db: Session) -> str:
    """Evaluates only the checks that have actually COMPLETED for this
    submission. Returns "ai_review_hard_failed" if any hard-gated check
    failed. Otherwise returns "ai_review_passed" — update51: this used to
    return "in_human_review" directly here, silently sending every
    submission straight to reviewers the instant checks finished, with no
    researcher-facing checkpoint at all. Now the researcher must review
    these results themselves and explicitly call POST .../submit-for-review
    (see submissions.py) to advance from "ai_review_passed" into
    "in_human_review" — and a hard-failed submission can never reach that
    endpoint successfully, so a hard gate failure now actually blocks
    something, rather than only being recorded."""
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

    new_status = "ai_review_hard_failed" if hard_failed else "ai_review_passed"
    sub.status = new_status
    db.commit()
    return new_status
