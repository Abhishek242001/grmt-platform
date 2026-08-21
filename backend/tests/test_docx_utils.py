import io
import zipfile

import pytest
from docx import Document

from app.ai.docx_utils import open_docx


def _make_legacy_namespace_docx(path: str) -> str:
    """Builds a real, valid .docx via python-docx, then rewrites its XML to
    use the alternate 'purl.oclc.org' namespace instead of the canonical
    'schemas.openxmlformats.org' one — reproducing the exact real-world
    pattern found in a genuine third-party-generated template (planning log
    §33), so this test exercises the real failure mode, not an invented one."""
    doc = Document()
    doc.add_paragraph("Body text in a legacy-namespace document.")
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    output = io.BytesIO()
    with zipfile.ZipFile(buf, "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                data = data.replace(
                    b"http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                    b"http://purl.oclc.org/ooxml/wordprocessingml/main",
                )
                data = data.replace(
                    b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                    b"http://purl.oclc.org/ooxml/officeDocument/relationships",
                )
            zout.writestr(item, data)

    with open(path, "wb") as f:
        f.write(output.getvalue())
    return path


def test_genuine_word_docx_opens_without_needing_the_fallback():
    """The common case — a real python-docx-generated file — must open on
    the first, fast path without ever needing normalization."""
    doc = Document()
    doc.add_paragraph("Ordinary body text.")
    path = "/tmp/_test_genuine_docx.docx"
    doc.save(path)

    opened = open_docx(path)
    assert opened.paragraphs[0].text == "Ordinary body text."


def test_standard_document_open_rejects_legacy_namespace_file():
    """Confirms the failure mode this fix addresses actually exists — a
    document.Document() call on a legacy-namespace file must fail the way
    the real file did, or this whole test file is testing the wrong thing."""
    path = _make_legacy_namespace_docx("/tmp/_test_legacy_ns_raw.docx")
    with pytest.raises(KeyError):
        Document(path)


def test_open_docx_falls_back_and_reads_legacy_namespace_file_correctly():
    path = _make_legacy_namespace_docx("/tmp/_test_legacy_ns.docx")
    doc = open_docx(path)
    assert doc.paragraphs[0].text == "Body text in a legacy-namespace document."
