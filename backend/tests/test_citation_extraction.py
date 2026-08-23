import pytest

from app.ai.citation_extraction import compare_citations, extract_citation_ids

# A realistic (hand-built, matching GROBID's documented output shape) TEI-XML
# fragment — deliberately NOT a full document, just the parts that matter:
# two in-text citation markers (one referencing b0, one referencing an id
# that has NO matching bibliography entry — b99, a deliberate broken
# reference) and a bibliography with two entries, one of which (b1) is
# never cited anywhere in the body.
_SAMPLE_TEI = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <teiHeader><fileDesc><titleStmt><title>Sample Paper</title></titleStmt></fileDesc></teiHeader>
  <text xml:lang="en">
    <body>
      <p>Prior work established this baseline <ref type="bibr" target="#b0">[1]</ref>.</p>
      <p>A follow-up study <ref type="bibr" target="#b99">[2]</ref> claimed otherwise, but was never published.</p>
    </body>
    <back>
      <div type="references">
        <listBibl>
          <biblStruct xml:id="b0">
            <analytic><title level="a">A Foundational Paper</title></analytic>
          </biblStruct>
          <biblStruct xml:id="b1">
            <analytic><title level="a">An Uncited Reference</title></analytic>
          </biblStruct>
        </listBibl>
      </div>
    </back>
  </text>
</TEI>
"""


def test_extracts_cited_ids_from_in_text_refs():
    result = extract_citation_ids(_SAMPLE_TEI)
    assert result["cited_ids"] == {"b0", "b99"}


def test_extracts_bibliography_ids():
    result = extract_citation_ids(_SAMPLE_TEI)
    assert result["bibliography_ids"] == {"b0", "b1"}


def test_ignores_non_bibliographic_refs():
    # <ref type="bibr"> is a citation; other ref types (figure/table refs,
    # already handled by table_figure_check.py) must NOT be picked up here.
    tei = """<?xml version="1.0"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0">
      <text><body>
        <p>See <ref type="bibr" target="#b0">[1]</ref> and <ref type="figure" target="#fig1">Fig. 1</ref>.</p>
      </body></text>
    </TEI>"""
    result = extract_citation_ids(tei)
    assert result["cited_ids"] == {"b0"}


def test_raises_value_error_for_malformed_xml():
    with pytest.raises(ValueError, match="Could not parse"):
        extract_citation_ids("<not><valid<xml")


def test_handles_document_with_no_citations_or_bibliography():
    tei = """<?xml version="1.0"?>
    <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><p>No citations here.</p></body></text></TEI>"""
    result = extract_citation_ids(tei)
    assert result["cited_ids"] == set()
    assert result["bibliography_ids"] == set()


# ── compare_citations — pure set logic, hand-verifiable ──────────────

def test_compare_citations_on_the_sample_fixture():
    extracted = extract_citation_ids(_SAMPLE_TEI)
    result = compare_citations(extracted["cited_ids"], extracted["bibliography_ids"])
    assert result["broken_citations"] == ["b99"]  # cited but no bibliography entry
    assert result["uncited_references"] == ["b1"]  # in bibliography but never cited
    assert result["total_citations"] == 2
    assert result["total_bibliography_entries"] == 2


def test_compare_citations_perfect_match_has_no_issues():
    result = compare_citations(cited_ids={"b0", "b1"}, bibliography_ids={"b0", "b1"})
    assert result["broken_citations"] == []
    assert result["uncited_references"] == []


def test_compare_citations_all_broken():
    result = compare_citations(cited_ids={"b0", "b1"}, bibliography_ids=set())
    assert result["broken_citations"] == ["b0", "b1"]
    assert result["uncited_references"] == []


def test_compare_citations_all_uncited():
    result = compare_citations(cited_ids=set(), bibliography_ids={"b0", "b1"})
    assert result["broken_citations"] == []
    assert result["uncited_references"] == ["b0", "b1"]


def test_compare_citations_empty_both():
    result = compare_citations(cited_ids=set(), bibliography_ids=set())
    assert result["broken_citations"] == []
    assert result["uncited_references"] == []
    assert result["total_citations"] == 0
