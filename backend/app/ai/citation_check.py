"""Citation completeness check — sends a PDF to a self-hosted GROBID
service (Docker, port 8070 by default — see PROJECT_HANDOFF.md for setup),
gets back TEI XML, and hands it to citation_extraction.py's already-tested
pure parsing/comparison logic.

PDF-only, same reasoning as format-compliance and the original page-limit/
column-count checks: GROBID processes PDFs specifically, not .docx. Unlike
those checks though, this ISN'T blocked on the Word->PDF pipeline being
PDF-only-capable — that pipeline already exists (see §4.1's Word-to-PDF
section), so a .docx submission gets converted to PDF first and GROBID
runs against the converted file, same pattern table_figure_check.py could
have used but didn't need to (it works directly on .docx too). Falls back
to reporting a clear "no PDF available" error for a .docx whose conversion
hasn't completed or failed, rather than crashing.

Uses httpx (already a project dependency, used by grammar_check.py for
LanguageTool) rather than adding a new HTTP client dependency.
"""
import os

import httpx

from app.ai.citation_extraction import compare_citations, extract_citation_ids

GROBID_URL = os.environ.get("GROBID_URL", "http://localhost:8070")
_TIMEOUT_SECONDS = 60  # GROBID's own docs suggest 5-10s typical, but scanned
# PDFs or long papers can run longer — generous but bounded, not infinite.


def _resolve_pdf_path(file_path: str) -> str:
    """GROBID needs a PDF specifically. If file_path is already a .pdf,
    use it directly. If it's a .docx, this check depends on the
    Word-to-PDF pipeline having already produced a converted PDF for this
    submission — the caller (submissions.py) is responsible for passing
    the CONVERTED path when available, not the raw .docx, since this
    module has no submission/version context of its own to look that up.
    Kept as a thin, explicit function rather than silently guessing, so
    the "wrong path type" failure mode is loud and traceable, not a
    confusing GROBID-side error."""
    if not file_path.lower().endswith(".pdf"):
        raise ValueError(
            f"Citation check requires a PDF; got {file_path}. "
            "Pass the converted PDF path for .docx submissions, not the original."
        )
    if not os.path.isfile(file_path):
        raise ValueError(f"PDF file not found: {file_path}")
    return file_path


def _call_grobid(pdf_path: str) -> str:
    """Real network call to the GROBID service — the one piece of this
    check that genuinely cannot be tested without GROBID actually running.
    Everything downstream of the TEI XML this returns (citation_extraction.py)
    is fully unit-tested without needing this function to ever execute."""
    with open(pdf_path, "rb") as f:
        response = httpx.post(
            f"{GROBID_URL}/api/processFulltextDocument",
            files={"input": (os.path.basename(pdf_path), f, "application/pdf")},
            timeout=_TIMEOUT_SECONDS,
        )
    response.raise_for_status()
    return response.text


def run_citation_check(file_path: str) -> dict:
    """Returns a dict shaped consistently with the other checks (status/
    issues/score), whether it succeeds or fails."""
    try:
        pdf_path = _resolve_pdf_path(file_path)
    except ValueError as e:
        return {"status": "error", "error": str(e), "issues": [], "score": None}

    try:
        tei_xml = _call_grobid(pdf_path)
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"GROBID returned an error: {e.response.status_code}", "issues": [], "score": None}
    except httpx.RequestError as e:
        return {"status": "error", "error": f"Could not reach GROBID service at {GROBID_URL}: {e}", "issues": [], "score": None}
    except Exception as e:
        # Broader net than the two httpx-specific branches above,
        # deliberately: a malformed/unexpected response (e.g. missing
        # attribute, unexpected shape) must degrade to a normal error
        # result too, not crash the whole checks_to_run loop in
        # submissions.py and take out every check queued after this one.
        return {"status": "error", "error": f"GROBID call failed unexpectedly: {e}", "issues": [], "score": None}

    try:
        extracted = extract_citation_ids(tei_xml)
    except ValueError as e:
        return {"status": "error", "error": f"Could not parse GROBID response: {e}", "issues": [], "score": None}

    comparison = compare_citations(extracted["cited_ids"], extracted["bibliography_ids"])

    issues = []
    for bib_id in comparison["broken_citations"]:
        issues.append(f"Citation references bibliography entry '{bib_id}', but no matching reference was found in the bibliography.")
    for bib_id in comparison["uncited_references"]:
        issues.append(f"Bibliography entry '{bib_id}' is never cited anywhere in the body text.")

    # Score reflects broken_citations only, not uncited_references — the
    # two are deliberately different severities (see citation_extraction.py's
    # compare_citations docstring): a broken citation is unambiguously a
    # defect, but an uncited bibliography entry could be a legitimate
    # "further reading" item some papers include on purpose. Weighting both
    # equally against the score would penalize a stylistic choice as if it
    # were the same kind of problem as a genuinely broken reference.
    score = (
        round(100 * (1 - len(comparison["broken_citations"]) / comparison["total_citations"]), 1)
        if comparison["total_citations"]
        else None
    )

    return {
        "status": "complete",
        "broken_citations": comparison["broken_citations"],
        "uncited_references": comparison["uncited_references"],
        "total_citations": comparison["total_citations"],
        "total_bibliography_entries": comparison["total_bibliography_entries"],
        "score": score,
        "issues": issues,
    }
