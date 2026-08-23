from unittest.mock import patch

import httpx
import pytest

from app.ai.citation_check import run_citation_check

_SAMPLE_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body>
    <p>Prior work <ref type="bibr" target="#b0">[1]</ref> and <ref type="bibr" target="#b99">[2]</ref>.</p>
  </body>
  <back><div type="references"><listBibl>
    <biblStruct xml:id="b0"><analytic><title level="a">Real Paper</title></analytic></biblStruct>
    <biblStruct xml:id="b1"><analytic><title level="a">Uncited Paper</title></analytic></biblStruct>
  </listBibl></div></back>
  </text>
</TEI>"""

_CLEAN_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <text><body>
    <p>Prior work <ref type="bibr" target="#b0">[1]</ref>.</p>
  </body>
  <back><div type="references"><listBibl>
    <biblStruct xml:id="b0"><analytic><title level="a">Real Paper</title></analytic></biblStruct>
  </listBibl></div></back>
  </text>
</TEI>"""


# ── file-path resolution — real logic, no mocking needed ────────────

def test_rejects_non_pdf_file_path(tmp_path):
    docx_path = tmp_path / "paper.docx"
    docx_path.write_bytes(b"not a real docx, just testing path rejection")
    result = run_citation_check(str(docx_path))
    assert result["status"] == "error"
    assert "requires a PDF" in result["error"]


def test_rejects_missing_pdf_file(tmp_path):
    result = run_citation_check(str(tmp_path / "does_not_exist.pdf"))
    assert result["status"] == "error"
    assert "not found" in result["error"]


# ── GROBID call — mocked, since a real GROBID service isn't available here ──

def test_returns_error_when_grobid_unreachable(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes for path-existence check")

    with patch("app.ai.citation_check._call_grobid", side_effect=httpx.RequestError("Connection refused")):
        result = run_citation_check(str(pdf_path))

    assert result["status"] == "error"
    assert "Could not reach GROBID" in result["error"]


def test_returns_error_on_grobid_http_error(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    mock_response = httpx.Response(503, request=httpx.Request("POST", "http://localhost:8070/api/processFulltextDocument"))
    with patch(
        "app.ai.citation_check._call_grobid",
        side_effect=httpx.HTTPStatusError("Service busy", request=mock_response.request, response=mock_response),
    ):
        result = run_citation_check(str(pdf_path))

    assert result["status"] == "error"
    assert "GROBID returned an error" in result["error"]
    assert "503" in result["error"]


def test_full_pipeline_with_mocked_grobid_response_finds_broken_and_uncited(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    with patch("app.ai.citation_check._call_grobid", return_value=_SAMPLE_TEI):
        result = run_citation_check(str(pdf_path))

    assert result["status"] == "complete"
    assert result["broken_citations"] == ["b99"]
    assert result["uncited_references"] == ["b1"]
    assert result["total_citations"] == 2
    assert len(result["issues"]) == 2
    assert any("b99" in issue and "no matching reference" in issue for issue in result["issues"])
    assert any("b1" in issue and "never cited" in issue for issue in result["issues"])


def test_clean_document_scores_100_with_no_issues(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    with patch("app.ai.citation_check._call_grobid", return_value=_CLEAN_TEI):
        result = run_citation_check(str(pdf_path))

    assert result["status"] == "complete"
    assert result["score"] == 100.0
    assert result["issues"] == []


def test_score_reflects_only_broken_citations_not_uncited_references(tmp_path):
    """Deliberate design confirmation: an uncited reference (potentially a
    legitimate 'further reading' entry) must NOT drag the score down the
    same way a genuinely broken citation does. Sample fixture has 1 broken
    out of 2 total citations -> score should be 50.0, not lower just
    because there's also 1 uncited reference."""
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    with patch("app.ai.citation_check._call_grobid", return_value=_SAMPLE_TEI):
        result = run_citation_check(str(pdf_path))

    assert result["score"] == 50.0


def test_returns_error_for_malformed_tei_response(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf bytes")

    with patch("app.ai.citation_check._call_grobid", return_value="<not><valid<xml"):
        result = run_citation_check(str(pdf_path))

    assert result["status"] == "error"
    assert "Could not parse GROBID response" in result["error"]
