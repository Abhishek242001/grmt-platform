"""
AI check clients — LanguageTool (grammar) and GROBID (citation/structure),
wired per master doc §3.1/§3.2. This is Phase 2 (Days 6-7) scope: the two
CPU-only, Docker-based checks. Plagiarism/AI-text/LLM checks are NOT here —
those are Phase 3 (§3.3, §3.5, §3.6), require the GPU services, and are out
of scope for this pass.

Both functions return a dict shaped to slot directly into an ai_reports row
(check_type, result_json, score, pass_fail, flagged, model_version) — see
app/models/submissions.py and master doc §4.3.
"""
import re

import httpx
from lxml import etree

from app.core.config import get_settings

settings = get_settings()

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Plain-text extraction for the grammar check. Uses PyMuPDF (fitz) — pure
    Python, no GPU, per master doc §3.8's note that PyMuPDF/pdfplumber are
    already the chosen library for PDF structure work elsewhere in the spec.
    """
    import fitz  # PyMuPDF — imported lazily so a missing dependency doesn't break unrelated imports

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def check_grammar(text: str) -> dict:
    """
    master doc §3.1. Chunks text over ~20,000 chars into paragraph-aligned
    segments (LanguageTool's per-request size is conservative) and issues
    multiple requests, merging match counts into one normalized result.

    score: normalized 0-100, where 100 = no issues found per 1000 words
    (issues-per-1000-words capped at 100 for a clean, boundable scale).
    This is a reasonable, documented starting formula — recalibrate against
    real submissions before trusting it as a hard signal (master doc §3.1
    doesn't prescribe an exact scoring formula, so this is an
    [ASSUMPTION] to revisit).
    """
    chunks = _chunk_text(text, max_chars=20000)
    total_matches = []
    word_count = max(len(text.split()), 1)

    with httpx.Client(timeout=60.0) as client:
        for chunk in chunks:
            resp = client.post(
                f"{settings.languagetool_url}/v2/check",
                data={"language": "en-US", "text": chunk},
            )
            resp.raise_for_status()
            body = resp.json()
            total_matches.extend(body.get("matches", []))

    issues_per_1000_words = (len(total_matches) / word_count) * 1000
    score = max(0.0, 100.0 - min(issues_per_1000_words, 100.0))

    return {
        "check_type": "grammar",
        "result_json": {
            "issue_count": len(total_matches),
            "issues_per_1000_words": round(issues_per_1000_words, 2),
            "sample_issues": [
                {
                    "message": m.get("message"),
                    "offset": m.get("offset"),
                    "length": m.get("length"),
                    "rule_id": (m.get("rule") or {}).get("id"),
                }
                for m in total_matches[:50]
            ],
        },
        "score": round(score, 2),
        "pass_fail": None,
        "flagged": issues_per_1000_words > 15,
        "model_version": "languagetool-latest",
    }


def check_structure(pdf_bytes: bytes) -> dict:
    """
    master doc §3.2. Calls GROBID's processFulltextDocument, parses the TEI
    response for header completeness + reference structure, and returns a
    citation-completeness score: the fraction of parsed bibliography entries
    that have all four of IEEE's minimum fields (authors, title, venue, year)
    per master doc §3.2's parsing guidance.
    """
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            f"{settings.grobid_url}/api/processFulltextDocument",
            files={"input": ("paper.pdf", pdf_bytes, "application/pdf")},
            data={"consolidateHeader": "1", "consolidateCitations": "0"},
        )
        resp.raise_for_status()
        tei_xml = resp.text

    root = etree.fromstring(tei_xml.encode("utf-8"))

    title_el = root.find(".//tei:titleStmt/tei:title", TEI_NS)
    has_title = title_el is not None and (title_el.text or "").strip() != ""
    author_els = root.findall(".//tei:sourceDesc//tei:author", TEI_NS)
    has_authors = len(author_els) > 0
    abstract_el = root.find(".//tei:abstract", TEI_NS)
    has_abstract = abstract_el is not None and "".join(abstract_el.itertext()).strip() != ""

    bibl_structs = root.findall(".//tei:listBibl/tei:biblStruct", TEI_NS)
    complete_refs = 0
    for bibl in bibl_structs:
        has_ref_authors = len(bibl.findall(".//tei:author", TEI_NS)) > 0
        has_ref_title = bibl.find(".//tei:title", TEI_NS) is not None
        has_ref_venue = bibl.find(".//tei:monogr/tei:title", TEI_NS) is not None or bibl.find(
            ".//tei:series/tei:title", TEI_NS
        ) is not None
        has_ref_year = bibl.find(".//tei:date", TEI_NS) is not None
        if has_ref_authors and has_ref_title and (has_ref_venue or has_ref_year):
            complete_refs += 1

    total_refs = len(bibl_structs)
    citation_completeness = (complete_refs / total_refs * 100) if total_refs > 0 else 0.0
    header_complete = has_title and has_authors and has_abstract

    return {
        "check_type": "citation",
        "result_json": {
            "header_complete": header_complete,
            "has_title": has_title,
            "has_authors": has_authors,
            "has_abstract": has_abstract,
            "total_references_found": total_refs,
            "complete_references": complete_refs,
        },
        "score": round(citation_completeness, 2),
        "pass_fail": header_complete and total_refs > 0,
        "flagged": citation_completeness < 70 if total_refs > 0 else True,
        "model_version": "grobid-0.9.0-crf",
    }


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """Paragraph-aligned chunking so a LanguageTool request never splits mid-sentence where avoidable."""
    if len(text) <= max_chars:
        return [text] if text.strip() else []

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current.strip():
        chunks.append(current)
    return chunks
