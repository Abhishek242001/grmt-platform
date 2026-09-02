from app.ai.ai_text_highlighting import (
    rect_to_percentage,
    resolve_chunk_pages,
    split_into_search_windows,
)


# ── split_into_search_windows ──

def test_splits_multiple_sentences():
    text = "This is the first sentence. This is the second sentence here. And a third one too."
    windows = split_into_search_windows(text)
    assert len(windows) == 3
    assert windows[0] == "This is the first sentence."
    assert windows[1] == "This is the second sentence here."
    assert windows[2] == "And a third one too."


def test_single_sentence_returns_one_window():
    text = "Just one single sentence with no other sentences in it."
    windows = split_into_search_windows(text)
    assert windows == [text]


def test_drops_windows_shorter_than_minimum():
    text = "OK. This is a genuinely long enough sentence to search for."
    windows = split_into_search_windows(text)
    # "OK." is far too short/generic to search for reliably — must be dropped,
    # not included as a window that could match dozens of unrelated places.
    assert "OK." not in windows
    assert len(windows) == 1


def test_empty_text_returns_no_windows():
    assert split_into_search_windows("") == []


def test_whitespace_only_text_returns_no_windows():
    assert split_into_search_windows("   \n\n  ") == []


# ── resolve_chunk_pages ──

def test_resolves_chunk_fully_within_one_page():
    page_map = [(0, 100, 1), (100, 250, 2), (250, 400, 3)]
    assert resolve_chunk_pages(page_map, 120, 200) == [2]


def test_resolves_chunk_spanning_two_pages():
    page_map = [(0, 100, 1), (100, 250, 2), (250, 400, 3)]
    # starts in page 1's range, ends in page 2's range
    assert resolve_chunk_pages(page_map, 80, 150) == [1, 2]


def test_resolves_chunk_exactly_on_boundary():
    page_map = [(0, 100, 1), (100, 250, 2)]
    # ends exactly where page 2 starts — should NOT count as touching page 2
    # (end_char is exclusive, matching Python slice semantics used
    # throughout this codebase's page_map handling elsewhere)
    assert resolve_chunk_pages(page_map, 0, 100) == [1]


def test_empty_page_map_returns_no_pages():
    assert resolve_chunk_pages([], 10, 20) == []


def test_none_page_map_returns_no_pages():
    """The real-world case for a .docx submission with no converted PDF —
    page_map is None, not an empty list."""
    assert resolve_chunk_pages(None, 10, 20) == []


def test_span_outside_any_known_page_returns_no_pages():
    page_map = [(0, 100, 1)]
    assert resolve_chunk_pages(page_map, 500, 600) == []


# ── rect_to_percentage ──

def test_converts_rect_to_percentage_of_page():
    # A 100x200pt box at (50,25) on a 200x400pt page (Letter-ish scale)
    result = rect_to_percentage(50, 25, 150, 225, page_width=200, page_height=400)
    assert result["xPct"] == 25.0  # 50/200
    assert result["yPct"] == 6.25  # 25/400
    assert result["wPct"] == 50.0  # (150-50)/200
    assert result["hPct"] == 50.0  # (225-25)/400


def test_rect_covering_whole_page_is_100_percent():
    result = rect_to_percentage(0, 0, 612, 792, page_width=612, page_height=792)
    assert result["xPct"] == 0.0
    assert result["yPct"] == 0.0
    assert result["wPct"] == 100.0
    assert result["hPct"] == 100.0


def test_zero_page_width_raises():
    try:
        rect_to_percentage(0, 0, 10, 10, page_width=0, page_height=100)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_zero_page_height_raises():
    try:
        rect_to_percentage(0, 0, 10, 10, page_width=100, page_height=0)
        assert False, "expected ValueError"
    except ValueError:
        pass
