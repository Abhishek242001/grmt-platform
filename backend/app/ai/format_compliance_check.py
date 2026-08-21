"""Publisher format-compliance check (feature #3 of the 8 AI-driven checks —
planning log §2). Deterministic and rule-based, matching this product's own
reasoning for the check (Discussion 4): "margins are 0.5in, IEEE requires
0.625in" is a fact, not an LLM's opinion, and this check can feed a hard
gate — it needs to be consistent and explainable every time, not vary run
to run the way an LLM judgment call would.

IEEE_RULES values are sourced verbatim from the master build document §3.7,
not invented. Springer's rule set doesn't exist yet (Discussion 3) — calling
this with publisher_format="springer" returns a clear error rather than
silently running IEEE's rules against a Springer paper.

Scope of this pass: page size, column count, margins, body font size, page
limit (PDF only — .docx page count isn't knowable without rendering, tied to
the still-pending Word->PDF pipeline), and structure presence (Abstract,
References, Roman-numeral section headings). Deferred — needs GROBID, not
yet stood up: citation-to-reference resolution, full section-order beyond
presence, equation numbering.
"""
import os
import re

from app.ai.grammar_check import _BODY_END_PATTERN, _BODY_START_PATTERN, extract_text

IEEE_RULES = {
    # Page-size-aware margins — IEEE does not have one universal format; it
    # varies by venue/journal, and page size (Letter vs A4) is one real axis
    # of that variation. Applying one margin spec regardless of detected
    # page size (the original version of this dict) was itself a bug, not
    # just having the wrong numbers (planning log §32-33).
    #
    # "letter" sourced from a genuine official IEEE conference full-paper
    # template's own explicit stated text (high confidence):
    #   - "should begin 1.0 inch (2.54 cm) from the top edge"
    #   - "the bottom margin should be 1-1/8 inches (2.86 cm)"
    #   - print area "6-7/8 inches (17.5 cm) wide" on an 8.5in page ->
    #     (8.5 - 6.875) / 2 = 0.8125in left/right
    #
    # "a4" sourced from a real A4-targeted IEEE-style template's stored XML
    # section properties, cross-referenced against Scribbr's IEEE format
    # guide. Lower confidence than "letter" — this specific template is a
    # third-party (Scribbr) recreation of IEEE style, not an IEEE-authored
    # document, so treat these numbers as a reasonable approximation pending
    # a genuine IEEE-authored A4 template to verify against directly.
    "page_sizes_in": {"letter": (8.5, 11.0), "a4": (8.27, 11.69)},
    "columns": 2,
    "margins_in": {
        "letter": {"top": 1.0, "bottom": 1.125, "left": 0.8125, "right": 0.8125},
        "a4": {"top": 0.75, "bottom": 1.0, "left": 0.62, "right": 0.62},
    },
    "body_font_size_pt": 10,
    "page_limit": 8,  # template's own stated hard maximum; real per-conference override belongs in gate_rules, not hardcoded here
}

_MARGIN_TOLERANCE_IN = 0.1  # measurement isn't pixel-perfect; allow reasonable slack
_FONT_TOLERANCE_PT = 1.0
_PAGE_SIZE_TOLERANCE_IN = 1.0
_ROMAN_SECTION_HEADING = re.compile(r"^[IVXLCDM]+\.\s+[A-Z]", re.MULTILINE)


def _closest_page_size(width_in: float, height_in: float):
    best_name, best_diff = None, float("inf")
    for name, (w, h) in IEEE_RULES["page_sizes_in"].items():
        diff = abs(width_in - w) + abs(height_in - h)
        if diff < best_diff:
            best_name, best_diff = name, diff
    return best_name if best_diff < _PAGE_SIZE_TOLERANCE_IN else None


def _effective_font_size(paragraph, run) -> float | None:
    """Font size, falling back through the style inheritance chain — many
    real .docx documents (confirmed against a real IEEE manuscript template,
    planning log §31) define font size via named paragraph styles (e.g. a
    style literally named "Abstract" or "Body Text Indent" carrying the
    formatting) rather than setting it explicitly on every run. Checking
    only run.font.size, as the original version of this function did, missed
    this entirely — it isn't a rare edge case, it's the normal way Word
    templates are actually built."""
    if run.font.size:
        return run.font.size.pt
    style = paragraph.style
    seen = set()
    while style is not None and id(style) not in seen:
        seen.add(id(style))
        if style.font.size:
            return style.font.size.pt
        style = style.base_style
    return None


def _measure_docx(file_path: str) -> dict:
    """Reads margins/page-size directly from the .docx's stored section
    properties — exact values, no measurement/inference needed (the format
    already stores them as explicit metadata). Column count isn't exposed as
    a simple python-docx property (would need raw XML digging into <w:cols>)
    — left as None rather than risk an untested guess."""
    from app.ai.docx_utils import open_docx

    doc = open_docx(file_path)
    # Last section, not first — real multi-section documents (confirmed
    # against a real file, planning log §33) often have a title-page-
    # specific first section with different, non-representative margins;
    # the last section is consistently the main-body formatting. Mirrors
    # the same reasoning already applied to PDF page selection (page index
    # 1, not 0) for the identical underlying reason.
    section = doc.sections[-1]

    font_sizes = []
    for p in doc.paragraphs[:30]:
        for run in p.runs:
            size = _effective_font_size(p, run)
            if size is not None:
                font_sizes.append(size)

    return {
        "page_width_in": round(section.page_width.inches, 2),
        "page_height_in": round(section.page_height.inches, 2),
        "margin_top_in": round(section.top_margin.inches, 2),
        "margin_bottom_in": round(section.bottom_margin.inches, 2),
        "margin_left_in": round(section.left_margin.inches, 2),
        "margin_right_in": round(section.right_margin.inches, 2),
        "columns": None,
        "body_font_size_pt": round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else None,
        "page_count": None,  # not knowable from .docx without rendering
    }


def _measure_pdf(file_path: str) -> dict:
    """Approximate measurement from the PDF's rendered layout — margins are
    inferred from the bounding box of actual text content vs. the page edge,
    not stored as exact metadata the way .docx margins are.

    Two real limitations, confirmed empirically (planning log §29), worth
    understanding rather than being surprised by:
    1. A published/typeset article (not a submission manuscript) has
       compiler-added running headers/footers/page numbers sitting close to
       the page edges — content §3.7 explicitly says a real manuscript
       shouldn't have. Measuring a published article's margins this way
       reads artificially small on every side; that's the wrong artifact
       type for this check, not a bug in it.
    2. Margin accuracy (especially the trailing edge — right margin in a
       standard left-to-right layout) depends on how consistently the
       actual text reaches the true column boundary. Real justified
       academic prose does this naturally; sparse or short lines don't,
       and will read a larger "margin" than the page's real design margin.
    """
    import pymupdf

    doc = pymupdf.open(file_path)
    if len(doc) == 0:
        doc.close()
        return {}

    page_count = len(doc)
    # Page 2 (index 1) if it exists — page 1 is often a single-column title/
    # abstract block before the two-column body starts, which would give a
    # misleading column-count/margin reading for the actual body layout.
    measure_index = 1 if page_count > 1 else 0
    page = doc[measure_index]

    page_width_in = page.rect.width / 72.0
    page_height_in = page.rect.height / 72.0

    blocks = page.get_text("blocks")
    text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]

    margins = {}
    if text_blocks:
        margins["margin_left_in"] = round(min(b[0] for b in text_blocks) / 72.0, 2)
        margins["margin_right_in"] = round(page_width_in - max(b[2] for b in text_blocks) / 72.0, 2)
        margins["margin_top_in"] = round(min(b[1] for b in text_blocks) / 72.0, 2)
        margins["margin_bottom_in"] = round(page_height_in - max(b[3] for b in text_blocks) / 72.0, 2)
    else:
        margins = {k: None for k in ("margin_left_in", "margin_right_in", "margin_top_in", "margin_bottom_in")}

    # Same left/right bucket heuristic as pdf_text_extraction.py's column split.
    midpoint = page.rect.width / 2
    left_has_content = any(b[0] < midpoint for b in text_blocks)
    right_has_content = any(b[0] >= midpoint for b in text_blocks)
    columns = 2 if (left_has_content and right_has_content) else 1

    font_sizes = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size"):
                    font_sizes.append(span["size"])

    doc.close()

    return {
        "page_width_in": round(page_width_in, 2),
        "page_height_in": round(page_height_in, 2),
        "columns": columns,
        "body_font_size_pt": round(sum(font_sizes) / len(font_sizes), 1) if font_sizes else None,
        "page_count": page_count,
        **margins,
    }


def run_format_compliance_check(file_path: str, publisher_format: str = "ieee") -> dict:
    if publisher_format.lower() != "ieee":
        return {
            "status": "error",
            "error": f"No rule set implemented yet for publisher_format={publisher_format!r} (only 'ieee' so far)",
            "issues": [], "checks_passed": 0, "checks_total": 0, "score": None,
        }

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".docx":
            measurements = _measure_docx(file_path)
        elif ext == ".pdf":
            measurements = _measure_pdf(file_path)
        else:
            return {"status": "error", "error": f"Unsupported file type: {ext}", "issues": [], "checks_passed": 0, "checks_total": 0, "score": None}
    except Exception as e:
        return {"status": "error", "error": f"Could not measure document layout: {e}", "issues": [], "checks_passed": 0, "checks_total": 0, "score": None}

    try:
        text, _ = extract_text(file_path)
    except Exception:
        text = ""

    issues = []
    checks_total = 0
    checks_passed = 0

    def check(condition: bool, message: str):
        nonlocal checks_total, checks_passed
        checks_total += 1
        if condition:
            checks_passed += 1
        else:
            issues.append(message)

    detected_page_size = None
    if measurements.get("page_width_in") is not None:
        detected_page_size = _closest_page_size(measurements["page_width_in"], measurements["page_height_in"])
        check(detected_page_size is not None, f"Page size ({measurements['page_width_in']}x{measurements['page_height_in']}in) doesn't match IEEE Letter or A4 specs")

    if measurements.get("columns") is not None:
        check(measurements["columns"] == IEEE_RULES["columns"], f"Expected {IEEE_RULES['columns']}-column format, detected {measurements['columns']} column(s)")

    # Margins are only checked when we know which page size we're comparing
    # against — guessing which spec to apply would be worse than not
    # checking at all (planning log §33). The unrecognized-page-size case is
    # already flagged above.
    if detected_page_size is not None:
        expected_margins = IEEE_RULES["margins_in"][detected_page_size]
        for side in ("top", "bottom", "left", "right"):
            key = f"margin_{side}_in"
            if measurements.get(key) is not None:
                expected = expected_margins[side]
                actual = measurements[key]
                check(
                    abs(actual - expected) <= _MARGIN_TOLERANCE_IN,
                    f"{side.capitalize()} margin should be ~{expected}in ({detected_page_size.upper()}), measured ~{actual}in",
                )

    if measurements.get("body_font_size_pt") is not None:
        expected_font = IEEE_RULES["body_font_size_pt"]
        actual_font = measurements["body_font_size_pt"]
        check(abs(actual_font - expected_font) <= _FONT_TOLERANCE_PT, f"Body font size should be ~{expected_font}pt, measured ~{actual_font}pt")

    if measurements.get("page_count") is not None:
        check(measurements["page_count"] <= IEEE_RULES["page_limit"], f"Page limit is typically {IEEE_RULES['page_limit']} pages, document has {measurements['page_count']}")

    check(bool(_BODY_START_PATTERN.search(text)), "No 'ABSTRACT' heading found")
    check(bool(_BODY_END_PATTERN.search(text)), "No 'REFERENCES' heading found")
    check(bool(_ROMAN_SECTION_HEADING.search(text)), "No Roman-numeral-style section headings found (e.g. 'I. INTRODUCTION')")

    score = round(100 * checks_passed / checks_total, 1) if checks_total else None

    return {
        "status": "complete",
        "publisher_format": publisher_format,
        "measurements": measurements,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "score": score,
        "issues": issues,
    }
