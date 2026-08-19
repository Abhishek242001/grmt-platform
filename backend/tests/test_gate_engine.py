import pytest

from app.core.gate_engine import GateRuleValidationError, evaluate_gate_rules, validate_gate_rules


def test_ai_content_pct_cannot_be_hard_gate():
    """Master doc §4.3/§5.2 — the single most important constraint in the product."""
    with pytest.raises(GateRuleValidationError, match="cannot be a hard gate"):
        validate_gate_rules([{"rule_type": "ai_content_pct", "is_hard_gate": True, "threshold_hard": 20}])


def test_plagiarism_pct_cannot_be_hard_gate():
    with pytest.raises(GateRuleValidationError, match="cannot be a hard gate"):
        validate_gate_rules([{"rule_type": "plagiarism_pct", "is_hard_gate": True, "threshold_hard": 10}])


def test_ai_content_pct_soft_gate_is_allowed():
    # should not raise
    validate_gate_rules([{"rule_type": "ai_content_pct", "is_hard_gate": False, "threshold_soft": 15}])


def test_format_compliance_hard_gate_is_allowed():
    # deterministic checks CAN be hard gates
    validate_gate_rules([{"rule_type": "format_compliance", "is_hard_gate": True, "threshold_hard": 1}])


def test_mixed_valid_and_invalid_rules_raises_on_the_invalid_one():
    with pytest.raises(GateRuleValidationError):
        validate_gate_rules(
            [
                {"rule_type": "format_compliance", "is_hard_gate": True},
                {"rule_type": "plagiarism_pct", "is_hard_gate": True, "threshold_hard": 10},
            ]
        )


def test_evaluate_hard_fail_blocks_submission():
    rules = [{"rule_type": "format_compliance", "is_hard_gate": True, "threshold_hard": 1}]
    report = {"format_compliance": {"pass_fail": False}}
    decision = evaluate_gate_rules(rules, report)
    assert decision.hard_fail is True
    assert "format_compliance" in decision.hard_fail_reasons


def test_evaluate_soft_flag_does_not_block_submission():
    rules = [{"rule_type": "plagiarism_pct", "is_hard_gate": False, "threshold_soft": 5}]
    report = {"plagiarism_pct": {"score": 8}}
    decision = evaluate_gate_rules(rules, report)
    assert decision.hard_fail is False
    assert "plagiarism_pct" in decision.soft_flags


def test_evaluate_even_a_maliciously_hard_flagged_ai_content_rule_cannot_hard_fail():
    """
    Defense in depth: even if a rule somehow got persisted with
    is_hard_gate=True on ai_content_pct (e.g. a bug elsewhere, a direct DB
    edit), the evaluator itself refuses to treat it as a hard gate.
    """
    rules = [{"rule_type": "ai_content_pct", "is_hard_gate": True, "threshold_hard": 10}]
    report = {"ai_content_pct": {"score": 50}}
    decision = evaluate_gate_rules(rules, report)
    assert decision.hard_fail is False
    assert "ai_content_pct" in decision.soft_flags


def test_evaluate_clean_pass_when_nothing_exceeds_thresholds():
    rules = [{"rule_type": "plagiarism_pct", "is_hard_gate": False, "threshold_soft": 10}]
    report = {"plagiarism_pct": {"score": 2}}
    decision = evaluate_gate_rules(rules, report)
    assert decision.hard_fail is False
    assert decision.soft_flags == []


def test_evaluate_missing_check_result_is_skipped_not_errored():
    rules = [{"rule_type": "citation_completeness", "is_hard_gate": True, "threshold_hard": 1}]
    decision = evaluate_gate_rules(rules, report={})  # check hasn't run yet
    assert decision.hard_fail is False


def test_evaluate_multiple_rules_any_hard_fail_wins():
    rules = [
        {"rule_type": "plagiarism_pct", "is_hard_gate": False, "threshold_soft": 5},
        {"rule_type": "format_compliance", "is_hard_gate": True, "threshold_hard": 1},
    ]
    report = {
        "plagiarism_pct": {"score": 8},
        "format_compliance": {"pass_fail": False},
    }
    decision = evaluate_gate_rules(rules, report)
    assert decision.hard_fail is True
    assert "plagiarism_pct" in decision.soft_flags
    assert "format_compliance" in decision.hard_fail_reasons
