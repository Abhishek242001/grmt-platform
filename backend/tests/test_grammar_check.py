from app.ai.grammar_check import (
    _ACRONYM_LIKE,
    _page_for_offset,
    _slice_page_map,
    _split_into_chunks,
    _trim_to_body,
    CHUNK_SIZE,
)


def test_trim_to_body_excludes_byline_and_references():
    text = (
        "A Survey of Industrial AIoT\n\n"
        "KAMRAN SATTAR AWAISI, QIANG YE\n\n"
        "Corresponding author: Qiang Ye\n\n"
        "ABSTRACT Internet of Things is important.\n\n"
        "I. INTRODUCTION\n\n"
        "This is the real body prose that should be checked.\n\n"
        "REFERENCES\n\n"
        "[1] K. S. Awaisi, S. Hussain, arXiv:1234.5678\n\n"
        "[2] Another citation, vol. 3, pp. 1-10.\n"
    )
    trimmed, start, end = _trim_to_body(text)
    assert "KAMRAN SATTAR AWAISI" not in trimmed
    assert "Corresponding author" not in trimmed
    assert "This is the real body prose" in trimmed
    assert "arXiv:1234.5678" not in trimmed
    assert trimmed.startswith("ABSTRACT")
    assert text[start:end] == trimmed


def test_trim_to_body_falls_back_to_full_text_when_markers_missing():
    text = "Just some plain text with no Abstract or References headings at all."
    trimmed, start, end = _trim_to_body(text)
    assert trimmed == text
    assert (start, end) == (0, len(text))


def test_trim_to_body_matches_real_manuscript_title_case_run_in_headings():
    """A real IEEE manuscript template (planning log §31) uses "Abstract"
    title-case as a run-in heading — "Abstract - text starts right here" —
    not the ALL-CAPS standalone-line style a published/typeset article uses.
    Both must be detected; this is the manuscript-shaped case specifically."""
    text = (
        "Paper Title\n\n"
        "Author Name\n\n"
        "Abstract - The Abstract and Index Terms text should be 10 point Times New Roman.\n\n"
        "Introduction\n\n"
        "Real body prose that should be checked goes here.\n\n"
        "References\n\n"
        "[1] Some citation here.\n"
    )
    trimmed, start, end = _trim_to_body(text)
    assert "Author Name" not in trimmed
    assert "Real body prose that should be checked" in trimmed
    assert "Some citation here" not in trimmed
    assert trimmed.startswith("Abstract")


def test_acronym_pattern_matches_technical_acronyms():
    for word in ["AIoT", "IoT", "IIoT", "PdM", "CPS"]:
        assert _ACRONYM_LIKE.search(word), f"{word} should match the acronym pattern"


def test_acronym_pattern_does_not_match_ordinary_capitalized_words():
    for word in ["Qiang", "This", "Grammar", "Industrial"]:
        assert not _ACRONYM_LIKE.search(word), f"{word} should NOT match the acronym pattern"


def test_split_into_chunks_does_not_split_short_text():
    text = "A short document that fits in one chunk."
    chunks = _split_into_chunks(text)
    assert chunks == [(0, text)]


def test_split_into_chunks_covers_the_entire_long_document():
    # Build text well over CHUNK_SIZE so it MUST be split into multiple chunks —
    # this is what proves full-document coverage isn't silently truncated.
    paragraphs = [f"This is paragraph number {i} with some real words in it." for i in range(2000)]
    text = "\n\n".join(paragraphs)
    assert len(text) > CHUNK_SIZE * 2  # sanity check the test text is actually long enough

    chunks = _split_into_chunks(text)
    assert len(chunks) > 1  # must actually be split, not silently truncated to one piece

    # Reassembling every chunk's text, in order, must reconstruct the original exactly.
    reconstructed = "".join(chunk_text for _, chunk_text in chunks)
    assert reconstructed == text

    # Every chunk must respect the size cap (with reasonable tolerance for the
    # single-oversized-paragraph edge case, not exercised by this test).
    for _, chunk_text in chunks:
        assert len(chunk_text) <= CHUNK_SIZE


def test_split_into_chunks_offsets_are_correct():
    paragraphs = [f"Paragraph {i} content here for testing offsets." for i in range(1500)]
    text = "\n\n".join(paragraphs)
    chunks = _split_into_chunks(text)
    for chunk_start, chunk_text in chunks:
        assert text[chunk_start:chunk_start + len(chunk_text)] == chunk_text


def test_page_for_offset_resolves_correctly():
    page_map = [(0, 100, 1), (100, 250, 2), (250, 400, 3)]
    assert _page_for_offset(page_map, 50) == 1
    assert _page_for_offset(page_map, 100) == 2
    assert _page_for_offset(page_map, 249) == 2
    assert _page_for_offset(page_map, 250) == 3
    assert _page_for_offset(page_map, 399) == 3
    assert _page_for_offset(page_map, 500) is None  # out of range, must not crash
    assert _page_for_offset(None, 50) is None


def test_slice_page_map_reanchors_correctly_after_trim():
    # Original page_map over a 400-char document.
    page_map = [(0, 100, 1), (100, 250, 2), (250, 400, 3)]
    # Simulate trimming to keep only [50:300) of the original text.
    sliced = _slice_page_map(page_map, 50, 300)

    # Offset 0 in the TRIMMED text corresponds to offset 50 in the original —
    # which was page 1 — so the sliced map's first entry should still map to page 1.
    assert _page_for_offset(sliced, 0) == 1
    # Offset 100 in trimmed text = offset 150 in original = page 2.
    assert _page_for_offset(sliced, 100) == 2
    # Last offset in trimmed text (249, since trimmed length is 250) = offset 299 in original = page 3.
    assert _page_for_offset(sliced, 249) == 3
