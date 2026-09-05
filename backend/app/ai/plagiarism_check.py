"""Plagiarism check orchestrator. Phase 1 (update43): self-submission via
plagiarism_scoring.py's TF-IDF/cosine comparison — see that module's
docstring for why TF-IDF, not BGE-M3/FAISS, for this phase. Phase 2
(update45): optional external-literature comparison via a real provider
(Winston AI currently — see winston_plagiarism_client.py), injected as a
callable rather than imported directly here, matching the same pattern
ai_content_pipeline.py already uses for its injectable `scorer` — keeps
this orchestrator free of any DB/encryption/HTTP knowledge (which provider
is active, decrypting its key, is entirely submissions.py's job) and fully
testable without a live database or network.

update46 — abstract-only external scanning: Winston charges 2 credits per
word, and a real full paper (confirmed against an actual arXiv IEEE paper
during testing this session: 4,681 words) costs far more than a free
2,000-credit account can afford in a single call — the client deliberately
does not auto-chunk long text into multiple calls, since that would spend
credits repeatedly without an explicit decision to do so each time. Given
that real constraint, external comparison is currently scoped to the
document's ABSTRACT only (reusing logical_consistency_scoring.py's already-
tested extract_abstract_and_conclusion(), not a new extraction function),
while self-submission comparison (free, no credits) continues to run
against the FULL document, unchanged. This is a deliberate, temporary
scope limit tied to free-tier credit economics, not a permanent design
choice — the natural place to lift it once there's a paid plan or a larger
credit budget is EXTERNAL_SCAN_FULL_DOCUMENT below.

This check is registered in NEVER_HARD_GATE (app/models/conferences.py) —
same category of risk as ai_text and logical_consistency: an automated
similarity score is informational for reviewers, never grounds for an
automatic rejection on its own. A human always makes the final call on
whether flagged overlap is genuine misconduct, permitted self-citation, or
a false positive from shared domain terminology.
"""
from app.ai.grammar_check import extract_text
from app.ai.logical_consistency_scoring import extract_abstract_and_conclusion
from app.ai.plagiarism_scoring import DEFAULT_FLAG_THRESHOLD, compute_similarity_scores
from app.core.logging_utils import get_logger

logger = get_logger("grmt.plagiarism_check")

# Flip to True once there's budget (a paid plan, or a larger credit pool)
# to scan full documents externally instead of just the abstract — see the
# module docstring above for why this exists and isn't a permanent limit.
EXTERNAL_SCAN_FULL_DOCUMENT = False


def run_plagiarism_check(
    file_path: str,
    candidates: list[dict],
    flag_threshold: float = DEFAULT_FLAG_THRESHOLD,
    external_check_fn=None,
) -> dict:
    """Returns a dict shaped consistently with every other check (status/
    issues/score), whether it succeeds or fails.

    candidates: list of {"submission_id": str, "text": str} — fetched by
    the caller (submissions.py), not this function — keeps this orchestrator
    testable without a live database, matching every other check's pattern
    in this project.

    external_check_fn (update45): optional callable, `str -> dict` matching
    winston_plagiarism_client.py's run_winston_plagiarism_check() return
    shape. None (the default) skips external comparison entirely — the
    report's "external" key is None, not a missing key, so callers never
    have to branch on a maybe-absent key. A real external-provider failure
    (API error, no credits, network issue) is caught here and reported
    inside "external" rather than failing the whole plagiarism check —
    self-submission comparison (which needs no external dependency) must
    still succeed even when the external provider doesn't.

    When external_check_fn is given but EXTERNAL_SCAN_FULL_DOCUMENT is
    False (the current default — see module docstring), the callable is
    invoked with just the extracted ABSTRACT text, not the full document.
    If no ABSTRACT section can be found, external comparison is skipped
    entirely with a clear reason in "external" — rather than silently
    falling back to sending the whole document (which would defeat the
    entire point of this credit-conservation limit) or crashing."""
    try:
        text, _page_map = extract_text(file_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}", "issues": [], "score": None, "external": None}

    if not text.strip():
        return {
            "status": "error",
            "error": "No extractable text found in document",
            "issues": [],
            "score": None,
            "external": None,
        }

    try:
        result = compute_similarity_scores(text, candidates, flag_threshold=flag_threshold)
    except ValueError as e:
        return {"status": "error", "error": str(e), "issues": [], "score": None, "external": None}

    issues = [
        f"Submission text is {m['similarity'] * 100:.1f}% similar to a prior submission "
        f"(id: {m['submission_id']}) — worth a reviewer's manual check, not an automatic finding of plagiarism."
        for m in result["matches"]
    ]

    # Score convention: 100 = no concerning overlap found (matches every
    # other check's "higher score is better" convention), scaled down by
    # the highest similarity found — NOT the same direction as
    # ai_content_pipeline's ai_generated_percentage (where LOWER is
    # better). Whoever wires this into gate_engine.py's CHECK_EVALUATORS
    # must use the correct comparison direction for THIS check specifically,
    # same caution already flagged for ai_text's inverted convention.
    score = round((1 - result["highest_similarity"]) * 100, 1)

    external = None
    if external_check_fn is None:
        logger.info("plagiarism check: no external_check_fn given — external comparison skipped entirely")
    else:
        if EXTERNAL_SCAN_FULL_DOCUMENT:
            external_input_text = text
        else:
            abstract = extract_abstract_and_conclusion(text)["abstract"]
            if not abstract:
                logger.info("plagiarism check: no ABSTRACT section found — external check will be skipped")
                external = {
                    "status": "error",
                    "error": (
                        "No ABSTRACT section found — external comparison is currently "
                        "limited to the abstract only (see EXTERNAL_SCAN_FULL_DOCUMENT), "
                        "and there's no abstract text to send."
                    ),
                }
                external_input_text = None
            else:
                logger.info("plagiarism check: found a %d-character abstract, sending it to the external provider", len(abstract))
                external_input_text = abstract

        if external_input_text is not None:
            try:
                external = external_check_fn(external_input_text)
            except Exception as e:
                # An unhandled exception from the external check (rather than
                # its own clean {"status": "error", ...} return) shouldn't take
                # down the whole plagiarism check — self-submission comparison
                # already succeeded above and is still worth reporting.
                external = {"status": "error", "error": f"External plagiarism check failed: {e}"}

        if external.get("status") == "complete":
            for m in external.get("matches", []):
                label = m.get("source_title") or m.get("source_url") or "an external source"
                issues.append(
                    f"Submission text is {m['similarity_pct']:.1f}% similar to {label} — "
                    "worth a reviewer's manual check, not an automatic finding of plagiarism."
                )
            # The combined score reflects whichever comparison found MORE
            # concerning overlap — a clean self-submission result
            # shouldn't mask a real external match, and vice versa.
            external_score = round(100 - external.get("overall_similarity_pct", 0), 1)
            score = min(score, external_score)

    return {
        "status": "complete",
        "score": score,
        "highest_similarity": result["highest_similarity"],
        "matches": result["matches"],
        "candidates_compared": result["candidates_compared"],
        "candidates_skipped_too_short": result["candidates_skipped_too_short"],
        "flag_threshold": flag_threshold,
        "external": external,
        "issues": issues,
    }
