from app.core.ai_checks import _clean_extracted_text


def test_dehyphenates_line_wrapped_words():
    raw = "This is a demonstration of auto-\nregressive models."
    cleaned = _clean_extracted_text(raw)
    assert "auto-\nregressive" not in cleaned
    assert "autoregressive" in cleaned


def test_does_not_join_a_genuine_end_of_sentence_hyphen_before_capital():
    raw = "The model is state-of-the-art-\nHowever, results vary."
    cleaned = _clean_extracted_text(raw)
    assert "art-\nHowever" not in cleaned
    assert "artHowever" not in cleaned


def test_truncates_at_references_heading():
    raw = "Our method outperforms baselines.\n\nReferences\n[1] Smith, J. Some Paper. 2020.\n[2] Doe, A. Another Paper. 2021."
    cleaned = _clean_extracted_text(raw)
    assert "Smith" not in cleaned
    assert "outperforms baselines" in cleaned


def test_truncates_at_numbered_references_heading():
    raw = "Conclusion text here.\n\n7. References\n[1] Vaswani, A. et al."
    cleaned = _clean_extracted_text(raw)
    assert "Vaswani" not in cleaned
    assert "Conclusion text here" in cleaned


def test_does_not_truncate_on_inline_mention_of_references():
    raw = "This section references prior work extensively.\n\nMore content follows here."
    cleaned = _clean_extracted_text(raw)
    assert "More content follows here" in cleaned


def test_collapses_single_newlines_but_preserves_paragraph_breaks():
    raw = "First line of a\nwrapped sentence.\n\nA new paragraph starts here."
    cleaned = _clean_extracted_text(raw)
    assert "First line of a wrapped sentence." in cleaned
    assert "\n\n" in cleaned


def test_collapses_repeated_whitespace():
    raw = "Too    many     spaces."
    cleaned = _clean_extracted_text(raw)
    assert "Too many spaces." in cleaned
