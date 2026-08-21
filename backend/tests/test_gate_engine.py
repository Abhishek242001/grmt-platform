import json

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
