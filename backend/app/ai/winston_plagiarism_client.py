"""Winston AI plagiarism-detection client (update45) — real external-
literature comparison, phase 2 of the plagiarism-check plan (phase 1 was
self-submission-only, see plagiarism_check.py/plagiarism_scoring.py).

Endpoint contract confirmed against Winston AI's own published OpenAPI spec
(docs.gowinston.ai/api-reference/v2/plagiarism/post) — not guessed. Real
constraints from that spec, enforced here:
- text must be 100-120,000 characters (their limit, not one we invented)
- 2 credits consumed per word processed — genuinely scarce on a free
  2,000-credit account (1,000 words total budget), so this module never
  calls the API with more text than the caller explicitly asked for, and
  never silently retries/re-calls in a way that would burn credits twice
  for one check.

Split the same way citation_check.py splits GROBID: a pure
prepare/validate/parse layer (fully testable, no network) and the actual
network call (genuinely untestable without a real API key and live network
access — neither available in the sandbox this was written in)."""
import os
import time

import httpx

WINSTON_API_URL = os.environ.get("WINSTON_API_URL", "https://api.gowinston.ai/v2/plagiarism")
_TIMEOUT_SECONDS = 60  # a full-document scan against many web sources is not a fast call

_MIN_TEXT_CHARS = 100
_MAX_TEXT_CHARS = 120_000  # Winston's own hard limit — not a guess


class WinstonApiError(Exception):
    """Raised for any non-200 response, carrying Winston's own real error
    code/description (per their documented 400/401/402/403/415/429/500/503
    responses) rather than a generic message — the caller needs to tell
    "wrong API key" (401) apart from "out of credits" (402) apart from
    "rate limited, retry later" (429), since each has a different real
    fix."""

    def __init__(self, status_code: int, error_code: str, description: str):
        self.status_code = status_code
        self.error_code = error_code
        self.description = description
        super().__init__(f"Winston AI API error {status_code} ({error_code}): {description}")


def validate_text_length(text: str) -> None:
    """Raises ValueError with a clear message if text is outside Winston's
    real 100-120,000 character bounds — checked BEFORE spending any credits
    on a call that would just come back as a 400, not after."""
    length = len(text)
    if length < _MIN_TEXT_CHARS:
        raise ValueError(f"Text is {length} characters — Winston AI requires at least {_MIN_TEXT_CHARS}")
    if length > _MAX_TEXT_CHARS:
        raise ValueError(
            f"Text is {length} characters — Winston AI allows at most {_MAX_TEXT_CHARS}. "
            "Truncate or chunk the text before calling; this client does not do that "
            "automatically, since chunking a long document into multiple calls multiplies "
            "the real credit cost and should be a deliberate choice, not an automatic one."
        )


def build_request_payload(text: str, language: str = "auto", excluded_sources: list[str] | None = None) -> dict:
    """Pure — builds the exact JSON body Winston's v2/plagiarism endpoint
    expects, per their published schema. Does not call validate_text_length
    itself (the caller should, before deciding to spend credits at all) —
    kept separate so a caller can inspect/log the payload without
    triggering the length check's side-effect-free but still-a-decision
    validation logic twice."""
    payload: dict = {"text": text, "language": language}
    if excluded_sources:
        payload["excluded_sources"] = excluded_sources
    return payload


def call_winston_plagiarism_api(api_key: str, text: str, language: str = "auto") -> dict:
    """The real network call — genuinely untestable without a live API key
    and network access, neither available in the sandbox this was written
    in. Raises WinstonApiError with Winston's own real error code/message
    for any non-200 response, or httpx's own exception types for a
    connection-level failure (timeout, DNS, etc.) — the caller (the
    orchestrator in plagiarism_check.py, or ultimately submissions.py's
    usage-logging call site) is responsible for catching these and
    recording them, same pattern as every other external-service call in
    this project."""
    validate_text_length(text)
    payload = build_request_payload(text, language=language)

    response = httpx.post(
        WINSTON_API_URL,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_TIMEOUT_SECONDS,
    )

    if response.status_code != 200:
        try:
            body = response.json()
            error_code = body.get("error", "UNKNOWN_ERROR")
            description = body.get("description", response.text)
        except Exception:
            error_code = "UNKNOWN_ERROR"
            description = response.text
        raise WinstonApiError(response.status_code, error_code, description)

    return response.json()


def parse_winston_response(raw: dict) -> dict:
    """Pure — converts Winston's real response shape (confirmed against
    their published schema) into this project's own plagiarism-check
    report shape, matching plagiarism_check.py's existing self-submission
    output structure (score/matches/issues) so the frontend report card
    can render both sources through one shared shape rather than two
    different ones depending on which phase found the match.

    Winston's per-source plagiarismFound[] gives real character offsets
    into the scanned text — stored here as-is (start_char/end_char) so a
    later pass can reuse the exact same page-mapping + PyMuPDF search_for()
    highlighting architecture already built for AI-text detection
    (ai_text_highlighting.py), rather than inventing a second one.

    update50: also surfaces each source's canAccess flag — a source can be
    listed (found as a real candidate) while still scoring 0% because
    Winston couldn't actually fetch and compare its full text (paywalled,
    crawler-blocked, etc.). Without this, a real published match showing
    0% looks like a false negative when it may just be an access failure —
    surfacing it here lets the report distinguish "genuinely not similar"
    from "couldn't check this one" instead of leaving that ambiguous."""
    result = raw.get("result", {})
    overall_similarity_pct = result.get("score", 0.0)

    matches = []
    for source in raw.get("sources", []):
        if source.get("is_excluded"):
            continue
        matches.append({
            "source_url": source.get("url"),
            "source_title": source.get("title"),
            "similarity_pct": source.get("score", 0.0),
            "plagiarized_word_count": source.get("plagiarismWords", 0),
            "can_access": source.get("canAccess"),
            "matched_spans": [
                {
                    "start_char": span.get("startIndex"),
                    "end_char": span.get("endIndex"),
                    "text": span.get("sequence"),
                }
                for span in source.get("plagiarismFound", [])
            ],
        })
    matches.sort(key=lambda m: m["similarity_pct"], reverse=True)

    return {
        "overall_similarity_pct": overall_similarity_pct,
        "word_count": result.get("textWordCounts", 0),
        "plagiarized_word_count": result.get("totalPlagiarismWords", 0),
        "source_count": result.get("sourceCounts", 0),
        "matches": matches,
        "credits_used": raw.get("credits_used"),
        "credits_remaining": raw.get("credits_remaining"),
    }


def run_winston_plagiarism_check(api_key: str, text: str, language: str = "auto") -> dict:
    """Orchestrator — calls the real API and parses the result, or returns
    a clean {"status": "error", ...} shape matching every other check in
    this project's own convention, rather than letting WinstonApiError
    propagate up to a caller that doesn't know how to handle it. Timing is
    captured here (not in the router) so it's available for
    ApiUsageLog.response_time_ms regardless of which caller eventually
    logs it."""
    start = time.monotonic()
    try:
        raw = call_winston_plagiarism_api(api_key, text, language=language)
        elapsed_ms = (time.monotonic() - start) * 1000
        parsed = parse_winston_response(raw)
        return {"status": "complete", "response_time_ms": elapsed_ms, **parsed}
    except WinstonApiError as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "status": "error",
            "response_time_ms": elapsed_ms,
            "error": str(e),
            "error_code": e.error_code,
            "http_status": e.status_code,
        }
    except ValueError as e:
        # validate_text_length failing before any network call was made —
        # no elapsed time worth recording, no credits spent.
        return {"status": "error", "response_time_ms": 0.0, "error": str(e), "error_code": "TEXT_LENGTH_INVALID"}
    except Exception as e:
        elapsed_ms = (time.monotonic() - start) * 1000
        return {"status": "error", "response_time_ms": elapsed_ms, "error": f"Request failed: {e}", "error_code": "REQUEST_FAILED"}
