import concurrent.futures

import pymupdf
import pytest
from docx import Document

from app.core.word_to_pdf import ConversionError, convert_to_pdf


def _make_docx(path: str, text: str) -> str:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


# ── real conversion, no mocking ─────────────────────────────────
#
# LibreOffice is a real, heavy external dependency, but it's genuinely
# installed and testable here — mocking it out would just test that a
# mock returns what we told it to, and miss real failure modes (like the
# permissive-garbage-input behavior found and documented below).

def test_converts_a_real_docx_to_a_real_readable_pdf(tmp_path):
    docx_path = _make_docx(str(tmp_path / "paper.docx"), "Real content for conversion testing.")
    out_dir = str(tmp_path / "out")

    result = convert_to_pdf(docx_path, out_dir)

    assert result.endswith("paper.pdf")
    doc = pymupdf.open(result)
    assert len(doc) >= 1
    assert "Real content for conversion testing." in doc[0].get_text()


def test_raises_conversion_error_for_missing_source_file(tmp_path):
    with pytest.raises(ConversionError, match="not found"):
        convert_to_pdf(str(tmp_path / "does_not_exist.docx"), str(tmp_path / "out"))


def test_garbage_input_produces_a_pdf_rather_than_erroring(tmp_path):
    """Documents real, confirmed LibreOffice behavior rather than an
    assumption: `soffice --convert-to` does NOT reject malformed/non-docx
    input with an error. It falls back to interpreting the raw bytes as
    plain text and produces a PDF containing that text verbatim — exit
    code 0, no stderr. This is a genuine upstream LibreOffice behavior,
    confirmed by directly inspecting the produced PDF's content, not an
    assumption. Practical implication: this conversion step cannot be
    relied on to validate that an uploaded .docx is well-formed — that's
    already python-docx's job (via open_docx(), used by the AI checks,
    which DOES raise loudly on a genuinely corrupt file)."""
    garbage_path = str(tmp_path / "garbage.docx")
    with open(garbage_path, "wb") as f:
        f.write(b"this is not a valid docx file at all")

    result = convert_to_pdf(garbage_path, str(tmp_path / "out"))

    doc = pymupdf.open(result)
    assert "this is not a valid docx file at all" in doc[0].get_text()


def test_concurrent_conversions_do_not_cross_contaminate(tmp_path):
    """Regression-style test for the exact real risk the per-call throwaway
    LibreOffice profile (`-env:UserInstallation=...`) exists to prevent:
    two conversions running at the same time sharing a profile can clash.
    Runs 3 real conversions concurrently and confirms each output contains
    only its own input's content — no swapped/corrupted results."""
    paths = [_make_docx(str(tmp_path / f"doc_{i}.docx"), f"Unique content number {i}.") for i in range(3)]

    def convert(i):
        return convert_to_pdf(paths[i], str(tmp_path / f"out_{i}"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(convert, range(3)))

    for i, result in enumerate(results):
        text = pymupdf.open(result)[0].get_text()
        assert f"Unique content number {i}." in text
