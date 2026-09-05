import json

import pytest

from app.ai.logical_consistency_scoring import (
    extract_abstract_and_conclusion,
    parse_llm_response,
)


# ── parse_llm_response — valid cases ────────────────────────────────

def test_parses_clean_consistent_response():
    raw = json.dumps({"consistent": True, "findings": []})
    result = parse_llm_response(raw)
    assert result["consistent"] is True
    assert result["findings"] == []


def test_parses_clean_inconsistent_response_with_findings():
    raw = json.dumps({
        "consistent": False,
        "findings": [{
            "abstract_claim": "achieves 95% accuracy",
            "conclusion_statement": "achieves approximately 80% accuracy",
            "explanation": "The accuracy figure differs between the abstract and conclusion.",
        }],
    })
    result = parse_llm_response(raw)
    assert result["consistent"] is False
    assert len(result["findings"]) == 1
    assert result["findings"][0]["abstract_claim"] == "achieves 95% accuracy"


def test_strips_markdown_json_fence():
    raw = "```json\n" + json.dumps({"consistent": True, "findings": []}) + "\n```"
    result = parse_llm_response(raw)
    assert result["consistent"] is True


def test_strips_markdown_fence_without_json_language_tag():
    raw = "```\n" + json.dumps({"consistent": True, "findings": []}) + "\n```"
    result = parse_llm_response(raw)
    assert result["consistent"] is True


def test_handles_leading_trailing_whitespace():
    raw = "  \n" + json.dumps({"consistent": True, "findings": []}) + "\n  "
    result = parse_llm_response(raw)
    assert result["consistent"] is True


# ── parse_llm_response — malformed/invalid cases ────────────────────

def test_rejects_invalid_json_syntax():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_llm_response("{consistent: true, findings: []}")  # unquoted keys, invalid JSON


def test_rejects_non_object_json():
    with pytest.raises(ValueError, match="Expected a JSON object"):
        parse_llm_response(json.dumps(["not", "an", "object"]))


def test_rejects_missing_consistent_field():
    with pytest.raises(ValueError, match="missing required field"):
        parse_llm_response(json.dumps({"findings": []}))


def test_rejects_missing_findings_field():
    with pytest.raises(ValueError, match="missing required field"):
        parse_llm_response(json.dumps({"consistent": True}))


def test_rejects_non_boolean_consistent():
    with pytest.raises(ValueError, match="must be a boolean"):
        parse_llm_response(json.dumps({"consistent": "true", "findings": []}))


def test_rejects_non_list_findings():
    with pytest.raises(ValueError, match="must be a list"):
        parse_llm_response(json.dumps({"consistent": False, "findings": "some finding"}))


def test_rejects_finding_missing_required_fields():
    raw = json.dumps({
        "consistent": False,
        "findings": [{"abstract_claim": "X"}],  # missing conclusion_statement, explanation
    })
    with pytest.raises(ValueError, match="missing required field"):
        parse_llm_response(raw)


def test_rejects_self_contradictory_consistent_true_with_findings():
    raw = json.dumps({
        "consistent": True,
        "findings": [{
            "abstract_claim": "X", "conclusion_statement": "Y", "explanation": "Z",
        }],
    })
    with pytest.raises(ValueError, match="self-contradictory"):
        parse_llm_response(raw)


def test_rejects_self_contradictory_consistent_false_with_no_findings():
    raw = json.dumps({"consistent": False, "findings": []})
    with pytest.raises(ValueError, match="self-contradictory"):
        parse_llm_response(raw)


# ── extract_abstract_and_conclusion — pure regex, hand-verifiable ──

def test_extracts_both_sections_present():
    text = (
        "TITLE OF PAPER\n\n"
        "ABSTRACT\n"
        "This paper achieves 95% accuracy on the benchmark.\n\n"
        "INTRODUCTION\n"
        "Some intro text here that should not be included.\n\n"
        "CONCLUSION\n"
        "We achieved approximately 80% accuracy in practice.\n\n"
        "REFERENCES\n"
        "[1] Some reference.\n"
    )
    result = extract_abstract_and_conclusion(text)
    assert "95% accuracy" in result["abstract"]
    assert "intro text" not in result["abstract"]
    assert "80% accuracy" in result["conclusion"]
    assert "Some reference" not in result["conclusion"]


def test_handles_plural_conclusions_heading():
    text = "ABSTRACT\nSome claim.\n\nCONCLUSIONS\nSome finding.\n\nREFERENCES\nStuff.\n"
    result = extract_abstract_and_conclusion(text)
    assert result["conclusion"] == "Some finding."


def test_returns_none_for_missing_abstract():
    text = "INTRODUCTION\nNo abstract here.\n\nCONCLUSION\nSome finding.\n"
    result = extract_abstract_and_conclusion(text)
    assert result["abstract"] is None
    assert result["conclusion"] == "Some finding."


def test_returns_none_for_missing_conclusion():
    text = "ABSTRACT\nSome claim.\n\nINTRODUCTION\nBody text with no conclusion section.\n"
    result = extract_abstract_and_conclusion(text)
    assert result["abstract"] == "Some claim."
    assert result["conclusion"] is None


def test_conclusion_at_end_of_document_with_no_trailing_section():
    text = "ABSTRACT\nSome claim.\n\nCONCLUSION\nFinal thoughts with no section after this."
    result = extract_abstract_and_conclusion(text)
    assert result["conclusion"] == "Final thoughts with no section after this."


def test_returns_none_for_both_when_neither_present():
    text = "Just some plain text with no section headings at all."
    result = extract_abstract_and_conclusion(text)
    assert result["abstract"] is None
    assert result["conclusion"] is None


# ── update36: real PDF-extracted-text layouts (no isolated heading line) ──

def test_extracts_abstract_when_heading_flows_into_body_on_same_line():
    # Confirmed against a real published IEEE Access paper — PDF text
    # extraction doesn't isolate the heading on its own line the way
    # python-docx paragraphs do.
    text = (
        "ABSTRACT Internet of Things (IoT) is an important technology "
        "used in many applications.\n"
        "INDEX TERMS Internet of Things, machine learning.\n"
        "I. INTRODUCTION\n"
        "Internet of Things is an important technology that can be integrated.\n"
    )
    result = extract_abstract_and_conclusion(text)
    assert result["abstract"] == "Internet of Things (IoT) is an important technology used in many applications."


def test_extracts_conclusion_with_numbered_prefix_and_inline_body():
    # "VIII. CONCLUSION" — a roman-numeral section number directly
    # preceding the heading word, itself flowing into body text with no
    # line break, exactly as it appeared in the real paper this was found
    # against.
    text = (
        "ABSTRACT Some claim about the results.\n"
        "VIII. CONCLUSION The intersection of two fields has led to a new paradigm.\n"
    )
    result = extract_abstract_and_conclusion(text)
    assert result["conclusion"] == "The intersection of two fields has led to a new paradigm."


def test_extracts_conclusion_with_arabic_numbered_prefix():
    text = "ABSTRACT Some claim.\n8. CONCLUSION Final remarks on the study.\n"
    result = extract_abstract_and_conclusion(text)
    assert result["conclusion"] == "Final remarks on the study."


def test_numbered_heading_boundary_still_stops_abstract_correctly():
    # The section-end boundary detector must also recognize a NUMBERED
    # next heading (e.g. "I. INTRODUCTION") as a stopping point, not just
    # an unnumbered all-caps one.
    text = (
        "ABSTRACT Some claim about the results reported here.\n"
        "I. INTRODUCTION\n"
        "This body text must not leak into the abstract.\n"
    )
    result = extract_abstract_and_conclusion(text)
    assert "must not leak" not in result["abstract"]
    assert result["abstract"] == "Some claim about the results reported here."
