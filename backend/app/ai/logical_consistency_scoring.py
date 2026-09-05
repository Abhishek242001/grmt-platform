"""Validates and parses the LLM's structured JSON response for the logical
consistency check — deliberately separated from logical_consistency_check.py's
Ollama HTTP client for the same reason every other check in this project
splits pure logic from external-service orchestration: this module has
zero network/model dependency and is fully unit-testable with hand-built
JSON strings, no Ollama service needs to be running to test it.

Scope, chosen deliberately narrow rather than "check the whole paper for
any inconsistency" (too vague a claim for an LLM to judge reliably, and
unfalsifiable in a test): this check compares the ABSTRACT's claims
against the CONCLUSION's claims specifically — a well-defined, checkable
question ("does the conclusion support what the abstract claims?"), not
an open-ended judgment call. Confirmed real cases this catches: a claimed
accuracy number that differs between abstract and conclusion, a claimed
contribution the conclusion doesn't actually revisit, a hedged/qualified
claim in the conclusion that the abstract stated unconditionally.

Even with Ollama's JSON-schema-constrained output (a real grammar-level
constraint, not just a hopeful prompt instruction — see
logical_consistency_check.py), defensive parsing still matters: schema
constraints control shape, not semantic correctness, and any client
should validate rather than trust blindly.
"""
import json
import re

REQUIRED_FIELDS = ("consistent", "findings")
REQUIRED_FINDING_FIELDS = ("abstract_claim", "conclusion_statement", "explanation")


def _strip_markdown_fences(raw: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ``` even when explicitly
    asked for raw JSON — strip this before attempting to parse, rather
    than failing on otherwise-valid JSON over a formatting habit."""
    stripped = raw.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", stripped, re.DOTALL)
    return match.group(1).strip() if match else stripped


def parse_llm_response(raw: str) -> dict:
    """Returns a validated dict with "consistent" (bool) and "findings"
    (list of dicts, each with abstract_claim/conclusion_statement/
    explanation). Raises ValueError with a clear message for any
    malformed or incomplete response — never returns a partial or
    silently-wrong structure."""
    cleaned = _strip_markdown_fences(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")

    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"LLM response missing required field(s): {missing}")

    if not isinstance(data["consistent"], bool):
        raise ValueError(f"'consistent' must be a boolean, got {type(data['consistent']).__name__}")

    if not isinstance(data["findings"], list):
        raise ValueError(f"'findings' must be a list, got {type(data['findings']).__name__}")

    for i, finding in enumerate(data["findings"]):
        if not isinstance(finding, dict):
            raise ValueError(f"findings[{i}] must be an object, got {type(finding).__name__}")
        missing_finding_fields = [f for f in REQUIRED_FINDING_FIELDS if f not in finding]
        if missing_finding_fields:
            raise ValueError(f"findings[{i}] missing required field(s): {missing_finding_fields}")

    # A real, worth-catching inconsistency in the model's OWN output: it
    # claims "consistent": true but still lists findings (or vice versa —
    # "consistent": false with an empty findings list, meaning it flagged
    # a problem but gave no specifics). Both are internally contradictory
    # responses from the model itself, not something a caller should
    # silently paper over.
    if data["consistent"] and data["findings"]:
        raise ValueError("LLM response is self-contradictory: 'consistent' is true but findings is non-empty")
    if not data["consistent"] and not data["findings"]:
        raise ValueError("LLM response is self-contradictory: 'consistent' is false but findings is empty")

    return {"consistent": data["consistent"], "findings": data["findings"]}


_NUMBERING_PREFIX = r"(?:(?:[IVXLCDM]+|\d+)[.\)]\s*)?"


def extract_abstract_and_conclusion(text: str) -> dict:
    """Pure regex-based section extraction — locates the ABSTRACT and
    CONCLUSION(S) sections by heading, up to the next all-caps heading
    or end of document. Returns {"abstract": str|None, "conclusion": str|None}
    — either can be None if not found, which the caller must handle (can't
    run this check meaningfully without both sections present).

    Handles two real-world layouts, confirmed against an actual published
    IEEE Access paper (update36):
    - .docx-style: heading alone on its own line, body starts on the next
      line (the original, still-supported case).
    - PDF-extracted-text style: the heading flows directly into the body
      text on the same line (e.g. "ABSTRACT Internet of Things..."), and a
      numbered section prefix may precede the heading itself (e.g. "VIII.
      CONCLUSION The intersection..."). PDF text extraction doesn't
      preserve the paragraph-per-line structure python-docx gives for free,
      so the heading is no longer guaranteed to be isolated."""
    def _find_heading_end(heading_pattern: str) -> int | None:
        match = re.search(rf"(?im)^\s*{_NUMBERING_PREFIX}{heading_pattern}\b", text)
        return match.end() if match else None

    def _find_next_heading_start(from_index: int) -> int | None:
        # Same "run of uppercase/space/hyphen, min 4 chars" trick as the
        # original: a mixed-case word (i.e. real body text) breaks the
        # character class immediately, so this naturally stops at the
        # heading/body boundary even when they share a line. Anchored to
        # start-of-line so it doesn't fire on capitalized acronyms
        # (IoT, AI, ROI) sitting mid-sentence.
        match = re.search(rf"(?m)^\s*{_NUMBERING_PREFIX}[A-Z][A-Z \-]{{3,}}\b", text[from_index:])
        return from_index + match.start() if match else None

    def _extract_section(heading_pattern: str) -> str | None:
        heading_end = _find_heading_end(heading_pattern)
        if heading_end is None:
            return None
        next_start = _find_next_heading_start(heading_end)
        section_text = text[heading_end:next_start] if next_start is not None else text[heading_end:]
        return section_text.strip() or None

    abstract = _extract_section(r"ABSTRACT")
    conclusion = _extract_section(r"CONCLUSIONS?")
    return {"abstract": abstract, "conclusion": conclusion}
