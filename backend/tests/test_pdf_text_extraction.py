import pymupdf

from app.ai.pdf_text_extraction import _clean_block_text, extract_text_from_pdf


def test_dehyphenates_line_wrapped_words():
    raw = "This is a com-\nputing example that spans a line wrap."
    cleaned = _clean_block_text(raw)
    assert "computing" in cleaned
    assert "com-" not in cleaned
    assert "com- puting" not in cleaned


def test_converts_remaining_newlines_to_spaces():
    raw = "This sentence wraps\nacross two lines\nwithin one paragraph."
    cleaned = _clean_block_text(raw)
    assert "\n" not in cleaned
    assert "wraps across two lines within one paragraph" in cleaned


def test_does_not_touch_legitimate_hyphenated_words_mid_line():
    raw = "This is a state-of-the-art method with no line wrap."
    cleaned = _clean_block_text(raw)
    assert "state-of-the-art" in cleaned


def test_collapses_double_spaces_created_by_cleanup():
    raw = "Word one-\n two after dehyphenation join."
    cleaned = _clean_block_text(raw)
    assert "  " not in cleaned


def test_strips_leading_and_trailing_whitespace():
    raw = "  \n  Some text with padding.  \n  "
    cleaned = _clean_block_text(raw)
    assert cleaned == "Some text with padding."


def _make_test_pdf(pages: list[str]) -> str:
    """Builds a real multi-page PDF via PyMuPDF's own writer, so this test
    exercises the actual extraction path against a real file, not a mock."""
    doc = pymupdf.open()
    for page_text in pages:
        page = doc.new_page()
        page.insert_text((50, 72), page_text)
    path = "/tmp/_test_multi_page.pdf"
    doc.save(path)
    doc.close()
    return path


def test_page_map_correctly_maps_offsets_to_source_pages():
    pdf_path = _make_test_pdf(["First page content here.", "Second page content here.", "Third page content here."])
    text, page_map = extract_text_from_pdf(pdf_path)

    assert len(page_map) == 3
    assert "First page" in text
    assert "Second page" in text
    assert "Third page" in text

    for start, end, page_number in page_map:
        assert start < end
        span_text = text[start:end]
        if page_number == 1:
            assert "First page" in span_text
        elif page_number == 2:
            assert "Second page" in span_text
        elif page_number == 3:
            assert "Third page" in span_text

    for i in range(len(page_map) - 1):
        assert page_map[i][1] <= page_map[i + 1][0]
