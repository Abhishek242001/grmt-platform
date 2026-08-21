"""Shared .docx-opening helper — used by both grammar_check.py and
format_compliance_check.py, since both need to open .docx files and both
can hit the same real-world compatibility gap (planning log §33).

Some real .docx files (confirmed against a genuine third-party-generated
template, not authored by Microsoft Word directly) use an old/alternate
"purl.oclc.org" transitional OOXML namespace instead of the canonical
"schemas.openxmlformats.org" one that python-docx's Package loader requires
exactly. Without this fallback, such files fail to open at all — not a
formatting-quality issue, a hard crash on otherwise-valid, readable content.
"""
import io
import re
import zipfile

from docx import Document
from docx.document import Document as DocumentObject

# purl.oclc.org/ooxml/{category}/{rest} -> schemas.openxmlformats.org/{category}/2006/{rest}
# Verified against a real file's actual namespace declarations (relationships,
# wordprocessingml, drawingml, math all follow this exact pattern).
_LEGACY_OOXML_NS = re.compile(rb'http://purl\.oclc\.org/ooxml/([^/"]+)/')


def _normalize_legacy_ooxml_namespace(file_path: str) -> io.BytesIO:
    """Rewrites every XML part inside the .docx zip to use the canonical
    OOXML namespace, entirely in memory — no temp file written to disk."""
    output = io.BytesIO()
    with zipfile.ZipFile(file_path, "r") as zin, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                data = _LEGACY_OOXML_NS.sub(rb"http://schemas.openxmlformats.org/\1/2006/", data)
            zout.writestr(item, data)
    output.seek(0)
    return output


def open_docx(file_path: str) -> DocumentObject:
    """Opens a .docx, falling back to namespace normalization only if the
    standard open fails — genuine Word-generated files (the overwhelming
    majority) pay no extra cost; only the rare non-standard file does."""
    try:
        return Document(file_path)
    except KeyError:
        normalized = _normalize_legacy_ooxml_namespace(file_path)
        return Document(normalized)
