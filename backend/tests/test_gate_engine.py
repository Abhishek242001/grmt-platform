import json

import pytest

from app.core.gate_engine import evaluate_submission_gates
from app.models.conferences import Conference, GateRule
from app.models.core import User
from app.models.submissions import AIReport, Submission


def _make_user(db, role="researcher", email="u@example.com"):
    from app.core.security import hash_password
    user = User(email=email, password_hash=hash_password("Password1"), full_name="Test", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_conference(db, organizer_id, name="Conf"):
    conf = Conference(organizer_id=organizer_id, name=name, publisher_format="ieee")
    db.add(conf)
    db.commit()
    db.refresh(conf)
    return conf


def _make_submission(db, conference_id, researcher_id, title="Paper"):
    sub = Submission(conference_id=conference_id, researcher_id=researcher_id, title=title, status="processing")
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _make_grammar_report(db, submission_id, score):
    report = AIReport(
        submission_id=submission_id,
        check_type="grammar",
        status="complete",
        result_json=json.dumps({"status": "complete", "score": score, "error_count": 0, "matches": []}),
    )
    db.add(report)
    db.commit()
    return report


def _db_session():
    from app.core import database as database_module
    return database_module.SessionLocal()


def test_hard_gate_failure_sets_hard_failed_status(client):
    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org1@example.com")
        conf = _make_conference(db, org.id)
        res = _make_user(db, role="researcher", email="res1@example.com")
        sub = _make_submission(db, conf.id, res.id)

        db.add(GateRule(conference_id=conf.id, check_type="grammar", is_hard_gate=True, threshold=75))
        db.commit()

        _make_grammar_report(db, sub.id, score=50)  # below threshold — should hard-fail

        new_status = evaluate_submission_gates(sub.id, db)
        assert new_status == "ai_review_hard_failed"
    finally:
        db.close()


def test_soft_gate_failure_does_not_hard_fail(client):
    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org2@example.com")
        conf = _make_conference(db, org.id)
        res = _make_user(db, role="researcher", email="res2@example.com")
        sub = _make_submission(db, conf.id, res.id)

        db.add(GateRule(conference_id=conf.id, check_type="grammar", is_hard_gate=False, threshold=75))
        db.commit()

        _make_grammar_report(db, sub.id, score=50)  # below threshold, but SOFT — must not hard-fail

        new_status = evaluate_submission_gates(sub.id, db)
        assert new_status == "in_human_review"
    finally:
        db.close()


def test_passing_score_results_in_human_review_not_ai_review_passed(client):
    """With only 1 of 7 checks implemented, the engine must never claim
    ai_review_passed — that would falsely imply the full pipeline ran clean."""
    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org3@example.com")
        conf = _make_conference(db, org.id)
        res = _make_user(db, role="researcher", email="res3@example.com")
        sub = _make_submission(db, conf.id, res.id)

        db.add(GateRule(conference_id=conf.id, check_type="grammar", is_hard_gate=True, threshold=75))
        db.commit()

        _make_grammar_report(db, sub.id, score=95)  # comfortably passes

        new_status = evaluate_submission_gates(sub.id, db)
        assert new_status == "in_human_review"
        assert new_status != "ai_review_passed"
    finally:
        db.close()


def test_no_gate_rule_configured_does_not_block(client):
    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org4@example.com")
        conf = _make_conference(db, org.id)
        res = _make_user(db, role="researcher", email="res4@example.com")
        sub = _make_submission(db, conf.id, res.id)
        # Deliberately no GateRule row created for this conference at all.

        _make_grammar_report(db, sub.id, score=10)  # terrible score, but nothing configured to gate on it

        new_status = evaluate_submission_gates(sub.id, db)
        assert new_status == "in_human_review"
    finally:
        db.close()


def _make_ai_text_report(db, submission_id, ai_generated_percentage):
    report = AIReport(
        submission_id=submission_id,
        check_type="ai_text",
        status="complete",
        result_json=json.dumps({
            "status": "complete",
            "ai_generated_percentage": ai_generated_percentage,
            "overall_verdict": "reject" if ai_generated_percentage >= 15.0 else "accept",  # baked-in default, deliberately IGNORED by the real evaluator
        }),
    )
    db.add(report)
    db.commit()
    return report


def test_ai_text_gate_rule_can_never_be_a_hard_gate(client):
    """NEVER_HARD_GATE = {"plagiarism", "ai_text"} in models/conferences.py
    is a deliberate safety decision, DB-enforced (defense-in-depth — also
    supposed to be checked at the API layer, but the DB is the last line
    of defense). Given everything found this session about AI-text
    detection's real false-positive risk (RADAR flagging real academic
    writing; even followsci missing/misjudging some samples), a
    submission must never be auto-rejected purely on an AI-detection
    score with no human ever looking at it — only flagged for review.
    Confirms this constraint is actually active, not just documented."""
    from sqlalchemy.exc import IntegrityError

    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org5@example.com")
        conf = _make_conference(db, org.id)

        db.add(GateRule(conference_id=conf.id, check_type="ai_text", is_hard_gate=True, threshold=15.0))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_ai_text_soft_gate_never_hard_fails_regardless_of_score(client):
    """Since ai_text can only ever be a SOFT gate (see above), even a
    badly-failing check (90% AI-generated, way over any reasonable
    threshold) must never push the submission to "ai_review_hard_failed"
    — it can only ever leave things at "in_human_review", where an actual
    person makes the final call. This is the end-to-end confirmation that
    the safety guarantee holds all the way through evaluate_submission_gates,
    not just at GateRule-creation time."""
    db = _db_session()
    try:
        org = _make_user(db, role="organizer", email="org6@example.com")
        conf = _make_conference(db, org.id)
        res = _make_user(db, role="researcher", email="res6@example.com")
        sub = _make_submission(db, conf.id, res.id)

        db.add(GateRule(conference_id=conf.id, check_type="ai_text", is_hard_gate=False, threshold=15.0))
        db.commit()

        _make_ai_text_report(db, sub.id, ai_generated_percentage=90.0)  # about as bad as it gets

        new_status = evaluate_submission_gates(sub.id, db)
        assert new_status == "in_human_review"
        assert new_status != "ai_review_hard_failed"
    finally:
        db.close()


def test_ai_text_passes_evaluator_inverted_comparison_direction():
    """Direct unit test of the evaluator function itself — since ai_text
    can never hard-gate (see above), evaluate_submission_gates' return
    value can't distinguish "evaluator said fail" from "evaluator said
    pass" for this check_type (both just land on "in_human_review"
    either way). Testing _ai_text_passes directly is the right tool here,
    not a workaround — same as how the pure math in binoculars_scoring.py
    etc. is tested directly rather than only through a full pipeline."""
    from app.core.gate_engine import _ai_text_passes

    # Above threshold (22% with a 15% max) — must fail. A copy-paste of
    # the >= pattern from every other evaluator in this file would
    # incorrectly treat this as passing.
    assert _ai_text_passes({"ai_generated_percentage": 22.0}, threshold=15.0) is False

    # Below threshold — passes.
    assert _ai_text_passes({"ai_generated_percentage": 5.0}, threshold=15.0) is True

    # Exactly at threshold — "must be under 15%" means exactly 15% fails,
    # matching aggregate_chunk_results' own strict-less-than semantics.
    assert _ai_text_passes({"ai_generated_percentage": 15.0}, threshold=15.0) is False

    # No threshold configured — informational only, never gates.
    assert _ai_text_passes({"ai_generated_percentage": 99.0}, threshold=None) is True

    # Check itself errored (no percentage in the result) — don't gate on
    # a failed check, same convention as every other evaluator.
    assert _ai_text_passes({"status": "error"}, threshold=15.0) is True


def test_ai_text_passes_evaluator_ignores_reports_own_baked_in_verdict():
    """Confirms the evaluator recomputes pass/fail from the raw percentage
    against whatever threshold IT'S given, rather than trusting the
    report's own "overall_verdict" field — which was computed with
    whatever default was in effect when the check ran (see
    ai_content_pipeline.py's DEFAULT_MAX_AI_PERCENTAGE), not necessarily
    the organizer's actual configured GateRule value. A report whose own
    stored verdict says "accept" (12% is under the 15% default) must
    still correctly FAIL against an organizer's stricter real 10% rule."""
    from app.core.gate_engine import _ai_text_passes

    result = {"ai_generated_percentage": 12.0, "overall_verdict": "accept"}  # its own baked-in verdict says accept
    assert _ai_text_passes(result, threshold=10.0) is False  # but the real, stricter threshold must reject it
