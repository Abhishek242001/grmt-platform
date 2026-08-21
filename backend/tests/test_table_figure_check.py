from docx import Document

from app.ai.table_figure_check import _numeral_to_int, run_table_figure_check


def _make_docx(path: str, paragraphs: list[str]) -> str:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return path


# ── _numeral_to_int ──────────────────────────────────────────────

def test_numeral_to_int_parses_arabic():
    assert _numeral_to_int("12") == 12


def test_numeral_to_int_parses_roman():
    assert _numeral_to_int("IV") == 4
    assert _numeral_to_int("I") == 1
    assert _numeral_to_int("IX") == 9


def test_numeral_to_int_returns_none_for_garbage():
    assert _numeral_to_int("banana") is None


# ── run_table_figure_check — consistent document (no issues) ────

def test_fully_consistent_document_has_no_issues(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "III. METHODOLOGY",
        "The pipeline has several stages, illustrated in Fig. 1 below.",
        "Fig. 1. Steps in the pipeline",
        "Results are summarized in Table I.",
        "TABLE I. RESULTS SUMMARY",
    ])
    result = run_table_figure_check(path)
    assert result["status"] == "complete"
    assert result["issues"] == []
    assert result["checks_total"] > 0
    assert result["score"] == 100.0


# ── caption without a matching in-text reference ─────────────────

def test_flags_caption_never_referenced_in_text(tmp_path):
    # Mirrors a real defect pattern found calibrating against an actual
    # published IEEE-style paper: a figure has a caption but is never
    # mentioned anywhere in the body prose.
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "III. METHODOLOGY",
        "Some introductory text about the pipeline with no figure mention.",
        "Fig1. Steps in document clustering",
        "More text continues here about something else entirely.",
    ])
    result = run_table_figure_check(path)
    assert any("captioned but never referenced" in i for i in result["issues"])


# ── in-text reference without a matching caption ─────────────────

def test_flags_reference_with_no_matching_caption(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "As shown in Fig. 3, the results improve over time.",
        "No caption for figure 3 exists anywhere in this document.",
    ])
    result = run_table_figure_check(path)
    assert any("referenced in the text but no matching caption" in i for i in result["issues"])


# ── numbering gaps ────────────────────────────────────────────────

def test_flags_numbering_gap(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "Fig. 1. First figure",
        "As discussed in Fig. 1.",
        "Fig. 3. Third figure, skipping two",
        "As discussed in Fig. 3.",
    ])
    result = run_table_figure_check(path)
    assert any("numbering has a gap" in i and "Figure" in i for i in result["issues"])


def test_flags_table_numbering_gap_with_roman_numerals(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "TABLE I. FIRST TABLE",
        "See Table I for details.",
        "TABLE III. THIRD TABLE, SKIPPING TWO",
        "See Table III for details.",
    ])
    result = run_table_figure_check(path)
    assert any("numbering has a gap" in i and "Table" in i for i in result["issues"])


# ── duplicate numbering ────────────────────────────────────────────

def test_flags_duplicate_caption_number(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "Fig. 1. First figure",
        "Fig. 1. A different figure reusing the same number",
        "As discussed in Fig. 1.",
    ])
    result = run_table_figure_check(path)
    assert any("duplicate numbering" in i for i in result["issues"])


# ── no tables/figures at all — not an error, just nothing to check ──

def test_document_with_no_tables_or_figures_is_not_an_error(tmp_path):
    path = _make_docx(str(tmp_path / "paper.docx"), [
        "ABSTRACT This paper has no tables or figures at all.",
        "I. INTRODUCTION",
        "Just plain prose here.",
    ])
    result = run_table_figure_check(path)
    assert result["status"] == "complete"
    assert result["figures_found"] is False
    assert result["tables_found"] is False
    assert result["issues"] == []
    assert result["checks_total"] == 0
    assert result["score"] is None


# ── error handling ──────────────────────────────────────────────

def test_returns_error_status_for_unsupported_file_type(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("Fig. 1. Something")
    result = run_table_figure_check(str(path))
    assert result["status"] == "error"
    assert result["issues"] == []
    assert result["score"] is None


def test_returns_error_status_for_empty_document(tmp_path):
    path = _make_docx(str(tmp_path / "empty.docx"), [])
    result = run_table_figure_check(path)
    assert result["status"] == "error"


# ── runs on real PDF extraction too (not just .docx) ──────────────

def test_runs_on_pdf_via_shared_extract_text(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "As shown in Fig. 1, results improve.")
    page.insert_text((72, 100), "Fig. 1. Improvement over time")
    path = str(tmp_path / "paper.pdf")
    doc.save(path)
    doc.close()

    result = run_table_figure_check(path)
    assert result["status"] == "complete"
    assert result["figures_found"] is True
