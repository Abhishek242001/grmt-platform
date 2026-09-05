"""Table/figure consistency check (feature #4 of the 8 AI-driven checks —
handoff doc §4.2, picked as the natural next check to build: no GPU, no
corpus dependency, reuses already-tested text-extraction infra).

Deterministic and rule-based, same reasoning as format-compliance
(format_compliance_check.py's docstring): "Figure 3 is captioned but never
referenced in the text" is a fact about the document, not an LLM's opinion,
so this check can safely feed a hard gate.

Unlike format-compliance (margins/columns/page-count — physical layout,
PDF-only), this check is pure TEXT analysis: does every table/figure
caption have a matching in-text reference, does every in-text reference
have a matching caption, and is the numbering sequential with no gaps or
duplicates. None of that needs PDF page geometry, so this check runs on
both .docx and .pdf via the same extract_text() dispatcher grammar_check.py
already uses (and gets PDF page numbers on flagged issues for free, via the
same page_map machinery).

Scope of this pass (v1): caption<->reference matching and numbering gaps/
duplicates, from the text alone. Deferred: actually verifying a table's
claimed column count or a figure's claimed image exists and isn't broken
(would need Camelot for table structure / real image-object inspection —
bigger lift, not needed for the "is everything referenced and numbered
right" pass this is).

IEEE convention (confirmed against the "Preparation of Papers for IEEE
Sponsored Conferences" template's own instructional text, and cross-checked
against a real published IEEE-formatted paper): figures use "Fig." (an
abbreviation used even at the start of a sentence) with Arabic numerals;
tables are never abbreviated and conventionally use Roman numerals, with
the caption placed ABOVE the table (below for figures). Real documents are
looser than the spec in practice — e.g. inconsistent spacing/punctuation
around the number ("Fig1." vs "Fig 2.") within the very same paper, and
some non-IEEE-authored templates use Arabic numerals for tables too. The
patterns below are deliberately tolerant of that real-world looseness
rather than assuming spec-perfect formatting.
"""
import re

from app.ai.grammar_check import extract_text

# A caption is recognized by its distinctive punctuation immediately after
# the number (period or colon) at the start of a line/paragraph — that's
# what a caption looks like ("Fig. 3. Sample output", "TABLE II. RESULTS").
# An in-text reference doesn't have that shape ("as shown in Fig. 3,",
# "Fig. 3 illustrates...", "(see Table II)").
_FIGURE_CAPTION = re.compile(r"(?im)^\s*Fig(?:ure)?s?\.?\s*(\d+)\s*[.:]")
_TABLE_CAPTION = re.compile(r"(?im)^\s*TABLE\s+([IVXLCDM]+|\d+)\s*[.:]")

# Broader — matches a caption's own text too (captions are a subset of this
# pattern), so per-number reference counts always include the caption line
# itself; a number is only "referenced" if its count exceeds its caption
# count. See _numbers_referenced_beyond_caption below.
_FIGURE_REFERENCE = re.compile(r"(?i)\bFig(?:ure)?s?\.?\s*(\d+)\b")
_TABLE_REFERENCE = re.compile(r"(?i)\bTables?\s+([IVXLCDM]+|\d+)\b")

_VALID_ROMAN = re.compile(r"^[IVXLCDM]+$")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _numeral_to_int(token: str) -> int | None:
    """Accepts either an Arabic numeral string or a Roman numeral string
    (tables conventionally use Roman; figures conventionally use Arabic,
    but some templates mix this up, so both patterns accept either)."""
    if token.isdigit():
        return int(token)
    if _VALID_ROMAN.match(token.upper()):
        total, prev = 0, 0
        for ch in reversed(token.upper()):
            val = _ROMAN_VALUES[ch]
            total += -val if val < prev else val
            prev = max(prev, val)
        return total if total > 0 else None
    return None


def _numbers_referenced_beyond_caption(reference_pattern, caption_pattern, text: str) -> dict[int, bool]:
    """Returns {numeral_value: has_true_in_text_reference} for every number
    that appears via EITHER pattern. "True" reference means the reference
    count for that number exceeds how many times it appears as a caption —
    i.e. it's mentioned somewhere other than just its own caption line."""
    ref_counts: dict[int, int] = {}
    for m in reference_pattern.finditer(text):
        val = _numeral_to_int(m.group(1))
        if val is not None:
            ref_counts[val] = ref_counts.get(val, 0) + 1

    caption_counts: dict[int, int] = {}
    for m in caption_pattern.finditer(text):
        val = _numeral_to_int(m.group(1))
        if val is not None:
            caption_counts[val] = caption_counts.get(val, 0) + 1

    all_numbers = set(ref_counts) | set(caption_counts)
    return {
        n: ref_counts.get(n, 0) > caption_counts.get(n, 0)
        for n in all_numbers
    }, caption_counts


def _check_kind(kind_label: str, caption_pattern, reference_pattern, text: str, issues: list, check_fn) -> None:
    referenced_map, caption_counts = _numbers_referenced_beyond_caption(reference_pattern, caption_pattern, text)

    for number in sorted(referenced_map):
        has_caption = number in caption_counts
        has_reference = referenced_map[number]
        check_fn(has_caption, f"{kind_label} {number} is referenced in the text but no matching caption was found")
        check_fn(has_reference, f"{kind_label} {number} is captioned but never referenced in the body text")

    for number, count in caption_counts.items():
        check_fn(count <= 1, f"{kind_label} {number} has {count} captions — duplicate numbering")

    captioned_numbers = sorted(caption_counts)
    if len(captioned_numbers) >= 2:
        expected = list(range(captioned_numbers[0], captioned_numbers[-1] + 1))
        missing = sorted(set(expected) - set(captioned_numbers))
        if missing:
            issues.append(
                f"{kind_label} numbering has a gap: found {captioned_numbers}, missing {missing}"
            )


def run_table_figure_check(file_path: str) -> dict:
    """Returns a dict always shaped the same way, whether it succeeds or
    fails, so callers never have to branch on a missing key (same contract
    as run_grammar_check / run_format_compliance_check)."""
    try:
        text, _page_map = extract_text(file_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}", "issues": [], "checks_passed": 0, "checks_total": 0, "score": None}

    if not text.strip():
        return {"status": "error", "error": "No extractable text found in document", "issues": [], "checks_passed": 0, "checks_total": 0, "score": None}

    issues: list[str] = []
    checks_total = 0
    checks_passed = 0

    def check(condition: bool, message: str):
        nonlocal checks_total, checks_passed
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            issues.append(message)

    _check_kind("Figure", _FIGURE_CAPTION, _FIGURE_REFERENCE, text, issues, check)
    _check_kind("Table", _TABLE_CAPTION, _TABLE_REFERENCE, text, issues, check)

    figures_found = bool(_FIGURE_CAPTION.search(text) or _FIGURE_REFERENCE.search(text))
    tables_found = bool(_TABLE_CAPTION.search(text) or _TABLE_REFERENCE.search(text))

    score = round(100 * checks_passed / checks_total, 1) if checks_total else None

    return {
        "status": "complete",
        "figures_found": figures_found,
        "tables_found": tables_found,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "score": score,
        "issues": issues,
    }
