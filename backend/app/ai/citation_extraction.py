"""Parses GROBID's TEI XML output to check citation completeness — every
in-text citation marker should have a matching bibliography entry, and
(more softly) every bibliography entry should be cited somewhere in the
text. Deliberately separated from citation_check.py's GROBID HTTP client
for the same reason every other check in this project splits pure logic
from external-service orchestration: this module has zero network
dependency and is fully unit-testable with hand-built TEI-XML fixtures,
no GROBID service needs to be running anywhere to test it.

TEI-XML shape this relies on (confirmed against GROBID's own documentation,
not assumed):
    In-text citation:  <ref type="bibr" target="#b0">[1]</ref>
    Bibliography entry: <listBibl><biblStruct xml:id="b0">...</biblStruct></listBibl>
The "b0" id is what links a citation marker to its bibliography entry —
this is GROBID's own linking convention, not something invented here.
"""
from lxml import etree

_TEI_NS = "http://www.tei-c.org/ns/1.0"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_NSMAP = {"tei": _TEI_NS}


def extract_citation_ids(tei_xml: str) -> dict:
    """Returns {"cited_ids": set[str], "bibliography_ids": set[str]} — the
    set of bibliography-entry ids actually referenced somewhere in the
    body text, and the set of ids that have a real bibliography entry.
    Both are the bare id (e.g. "b0"), with the "#" target prefix stripped."""
    try:
        root = etree.fromstring(tei_xml.encode("utf-8") if isinstance(tei_xml, str) else tei_xml)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Could not parse TEI XML: {e}")

    cited_ids = set()
    for ref in root.iter(f"{{{_TEI_NS}}}ref"):
        if ref.get("type") != "bibr":
            continue
        target = ref.get("target")
        if target and target.startswith("#"):
            cited_ids.add(target[1:])

    bibliography_ids = set()
    for bibl_struct in root.iter(f"{{{_TEI_NS}}}biblStruct"):
        xml_id = bibl_struct.get(f"{{{_XML_NS}}}id")
        if xml_id:
            bibliography_ids.add(xml_id)

    return {"cited_ids": cited_ids, "bibliography_ids": bibliography_ids}


def compare_citations(cited_ids: set, bibliography_ids: set) -> dict:
    """Pure set comparison — split out from extract_citation_ids so the
    comparison logic itself (not just the XML parsing) has its own
    dedicated, trivially-hand-verifiable tests.

    broken_citations: referenced in text but no bibliography entry exists
        — a real defect, something is cited that isn't actually listed.
    uncited_references: a bibliography entry exists but is never cited in
        the text — a much softer signal (could be a genuinely unused
        reference left in by mistake, but could also be a legitimate
        "further reading" entry some papers include) — reported
        separately, not folded into the same severity."""
    broken_citations = cited_ids - bibliography_ids
    uncited_references = bibliography_ids - cited_ids
    return {
        "broken_citations": sorted(broken_citations),
        "uncited_references": sorted(uncited_references),
        "total_citations": len(cited_ids),
        "total_bibliography_entries": len(bibliography_ids),
    }
