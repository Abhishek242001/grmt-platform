"""Logical consistency check — compares a paper's abstract against its
conclusion for contradictions, using Qwen2.5-7B-Instruct via a self-hosted
Ollama service. The first genuinely LLM-judgment-based check in this
project (every other check is deterministic extraction/comparison) — see
PROJECT_HANDOFF.md for why the scope was deliberately narrowed to
abstract-vs-conclusion rather than "check the whole paper for any
inconsistency," and logical_consistency_scoring.py for the parsing logic
this depends on.

Uses Ollama's JSON-schema-constrained structured output (the `format`
parameter as a JSON Schema object, not just `"format": "json"`) — this is
a real grammar-level constraint enforced during generation, not a hopeful
prompt instruction, though logical_consistency_scoring.py's defensive
parsing still applies: schema constraints control shape, not semantic
correctness.

Same disclosure as every GPU/external-service-dependent check this
session: written where the actual service (Ollama + Qwen2.5-7B) could not
be run. The prompt and orchestration logic are structurally sound but
UNVERIFIED beyond a syntax/AST check — needs a real run on the GPU Studio
before being trusted. temperature=0 is set for determinism, which matters
more here than for a stylistic task, since inconsistent outputs on
identical input would undermine any confidence in the result.
"""
import os

import httpx

from app.ai.grammar_check import extract_text
from app.ai.logical_consistency_scoring import extract_abstract_and_conclusion, parse_llm_response

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_ID = "qwen2.5:7b-instruct"
_TIMEOUT_SECONDS = 120  # a 7B model's full response, unhurried — generous but bounded

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "consistent": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "abstract_claim": {"type": "string"},
                    "conclusion_statement": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["abstract_claim", "conclusion_statement", "explanation"],
            },
        },
    },
    "required": ["consistent", "findings"],
}

_PROMPT_TEMPLATE = """You are reviewing an academic paper for internal consistency. Compare the paper's ABSTRACT against its CONCLUSION.

Look specifically for:
- A claim, number, or result stated in the abstract that the conclusion states differently (e.g. a different accuracy figure, a different dataset size, a different claimed contribution)
- A claim the abstract states unconditionally that the conclusion hedges, qualifies, or contradicts
- A contribution or finding claimed in the abstract that the conclusion does not support or mention at all

Do NOT flag: minor wording differences that don't change the actual claim, or additional detail in the conclusion that doesn't contradict the abstract (elaboration is fine, contradiction is not).

ABSTRACT:
{abstract}

CONCLUSION:
{conclusion}

Respond with a JSON object matching this exact shape: {{"consistent": true/false, "findings": [{{"abstract_claim": "...", "conclusion_statement": "...", "explanation": "..."}}]}}. If everything is consistent, "consistent" must be true and "findings" must be an empty list. If you find any inconsistency, "consistent" must be false and "findings" must list each one."""


def _call_ollama(abstract: str, conclusion: str) -> str:
    """Real network call to the Ollama service — the one piece of this
    check that genuinely cannot be tested without Ollama + the model
    actually running. Everything downstream of the JSON string this
    returns (logical_consistency_scoring.py) is fully unit-tested without
    needing this function to ever execute."""
    prompt = _PROMPT_TEMPLATE.format(abstract=abstract, conclusion=conclusion)
    response = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": prompt}],
            "format": _RESPONSE_SCHEMA,
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def run_logical_consistency_check(file_path: str) -> dict:
    """Returns a dict shaped consistently with the other checks (status/
    issues/score), whether it succeeds or fails."""
    try:
        text, _page_map = extract_text(file_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}", "issues": [], "score": None}

    if not text.strip():
        return {"status": "error", "error": "No extractable text found in document", "issues": [], "score": None}

    sections = extract_abstract_and_conclusion(text)
    if not sections["abstract"] or not sections["conclusion"]:
        missing = []
        if not sections["abstract"]:
            missing.append("abstract")
        if not sections["conclusion"]:
            missing.append("conclusion")
        return {
            "status": "error",
            "error": f"Could not locate a {' and '.join(missing)} section — this check needs both to compare.",
            "issues": [],
            "score": None,
        }

    try:
        raw_response = _call_ollama(sections["abstract"], sections["conclusion"])
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"Ollama returned an error: {e.response.status_code}", "issues": [], "score": None}
    except httpx.RequestError as e:
        return {"status": "error", "error": f"Could not reach Ollama service at {OLLAMA_URL}: {e}", "issues": [], "score": None}
    except Exception as e:
        # Same reasoning as citation_check.py's equivalent broad except —
        # an unexpected response shape must degrade gracefully, not crash
        # the whole checks_to_run loop and take out every check after it.
        return {"status": "error", "error": f"Ollama call failed unexpectedly: {e}", "issues": [], "score": None}

    try:
        result = parse_llm_response(raw_response)
    except ValueError as e:
        return {"status": "error", "error": f"Could not parse Ollama response: {e}", "issues": [], "score": None}

    issues = [
        f"Abstract claims \"{f['abstract_claim']}\" but the conclusion states \"{f['conclusion_statement']}\" — {f['explanation']}"
        for f in result["findings"]
    ]

    return {
        "status": "complete",
        "consistent": result["consistent"],
        "findings": result["findings"],
        "score": 100.0 if result["consistent"] else 0.0,
        "issues": issues,
    }
