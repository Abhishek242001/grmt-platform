"""
Gate Rule Engine — master build document §2.5 / Figure 2, and the
non-negotiable product constraint from §1.1/§1.4: AI-content and
plagiarism/similarity checks can never be configured as a hard (auto-reject)
gate, only as a soft flag. This module is the single place that constraint is
enforced in code — both when an organizer saves gate rules AND when a
submission's checks are evaluated against them, so a rule that somehow got
into the database as a hard gate on one of these types still cannot cause an
auto-reject at evaluation time either.
"""
from dataclasses import dataclass, field

# rule_type values whose signal is a statistical/embedding-derived estimate,
# not a literal/deterministic fact — these carry real false-positive risk
# against non-native-English writing (master doc §1.7, §3.6) and so can never
# be a hard gate. Exact-match plagiarism evidence (MinHash) is deliberately
# NOT in this list — see master doc §1.4's note on that distinction.
NEVER_HARD_GATE_RULE_TYPES = {"ai_content_pct", "plagiarism_pct"}


class GateRuleValidationError(ValueError):
    """Raised when a gate-rule configuration violates the hard-gate constraint."""


def validate_gate_rules(rules: list[dict]) -> None:
    """
    Call this before persisting any gate-rule configuration (organizer save,
    admin import, seed script — anywhere rules are written). Raises
    GateRuleValidationError with a clear message if violated; the API layer
    (routers/conferences.py) turns this into a 422 per master doc §5.2.
    """
    for rule in rules:
        rule_type = rule.get("rule_type")
        is_hard = bool(rule.get("is_hard_gate", False))
        if rule_type in NEVER_HARD_GATE_RULE_TYPES and is_hard:
            raise GateRuleValidationError(
                f"'{rule_type}' cannot be a hard gate — see master build document "
                f"§1.1/§1.4 and development_rule.md for why this is a fixed product "
                f"constraint, not a configurable preference."
            )


@dataclass
class GateDecision:
    hard_fail: bool
    hard_fail_reasons: list[str] = field(default_factory=list)
    soft_flags: list[str] = field(default_factory=list)


def evaluate_gate_rules(rules: list[dict], report: dict) -> GateDecision:
    """
    rules: list of gate_rules rows (as dicts) for one conference.
    report: dict keyed by rule_type/check_type, each value having at least
            one of {"score": number, "pass_fail": bool}. This mirrors the
            per-check ai_reports rows for one submission version.

    Returns a GateDecision. Per master doc Figure 2: ANY hard fail -> reject.
    Otherwise, all soft flags attach and the submission proceeds to review.
    """
    decision = GateDecision(hard_fail=False)

    for rule in rules:
        rule_type = rule.get("rule_type")
        intended_hard = bool(rule.get("is_hard_gate", False))
        # A rule_type in NEVER_HARD_GATE_RULE_TYPES is downgraded to a soft
        # gate no matter what is_hard_gate says (defense in depth — this
        # mirrors validate_gate_rules() but must ALSO hold at evaluation
        # time in case an invalid rule ever reached the database some other
        # way, e.g. a direct DB edit bypassing the API).
        is_hard = intended_hard and rule_type not in NEVER_HARD_GATE_RULE_TYPES
        was_downgraded = intended_hard and not is_hard

        result = report.get(rule_type)
        if result is None:
            continue  # check hasn't produced a result yet / not configured for this run

        exceeded_hard = _exceeds(result, rule.get("threshold_hard"))
        exceeded_soft = _exceeds(result, rule.get("threshold_soft"))
        # A downgraded rule's "hard" threshold is still a meaningful signal —
        # it becomes the effective soft threshold rather than being ignored.
        exceeded_downgraded = was_downgraded and _exceeds(result, rule.get("threshold_hard"))

        if is_hard and exceeded_hard:
            decision.hard_fail = True
            decision.hard_fail_reasons.append(rule_type)
        elif exceeded_soft or exceeded_downgraded:
            decision.soft_flags.append(rule_type)
        elif result.get("pass_fail") is False:
            # deterministic checks (format compliance) that fail without a
            # numeric threshold at all
            if is_hard:
                decision.hard_fail = True
                decision.hard_fail_reasons.append(rule_type)
            else:
                decision.soft_flags.append(rule_type)

    return decision


def _exceeds(result: dict, threshold) -> bool:
    if threshold is None:
        return False
    score = result.get("score")
    if score is None:
        return False
    return float(score) > float(threshold)
