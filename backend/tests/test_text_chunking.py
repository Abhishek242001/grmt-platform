import pytest

from app.ai.text_chunking import chunk_text_by_words


def test_single_chunk_when_text_shorter_than_chunk_size():
    text = "one two three four five"
    chunks = chunk_text_by_words(text, words_per_chunk=10)
    assert len(chunks) == 1
    assert chunks[0]["word_count"] == 5
    assert chunks[0]["text"] == text


def test_splits_into_exact_chunks_when_evenly_divisible():
    text = "a b c d e f"  # 6 words
    chunks = chunk_text_by_words(text, words_per_chunk=2)
    assert len(chunks) == 3
    assert [c["word_count"] for c in chunks] == [2, 2, 2]
    assert chunks[0]["text"] == "a b"
    assert chunks[1]["text"] == "c d"
    assert chunks[2]["text"] == "e f"


def test_last_chunk_is_smaller_when_not_evenly_divisible():
    text = "a b c d e"  # 5 words
    chunks = chunk_text_by_words(text, words_per_chunk=2)
    assert [c["word_count"] for c in chunks] == [2, 2, 1]
    assert chunks[-1]["text"] == "e"


def test_start_and_end_char_point_into_original_text():
    text = "hello world foo bar"
    chunks = chunk_text_by_words(text, words_per_chunk=2)
    first, second = chunks
    assert text[first["start_char"]:first["end_char"]] == "hello world"
    assert text[second["start_char"]:second["end_char"]] == "foo bar"


def test_preserves_original_whitespace_within_a_chunk():
    # Multiple spaces / a newline between words — start_char/end_char slice
    # the ORIGINAL text, so original formatting between words is preserved
    # in the chunk's own text, not collapsed to single spaces.
    text = "hello    world\nfoo bar"
    chunks = chunk_text_by_words(text, words_per_chunk=3)
    assert chunks[0]["text"] == "hello    world\nfoo"


def test_rejects_empty_text():
    with pytest.raises(ValueError, match="must not be empty"):
        chunk_text_by_words("")


def test_rejects_whitespace_only_text():
    with pytest.raises(ValueError, match="must not be empty"):
        chunk_text_by_words("   \n\n   ")


def test_rejects_non_positive_words_per_chunk():
    with pytest.raises(ValueError, match="must be positive"):
        chunk_text_by_words("some real text", words_per_chunk=0)


def test_realistic_chunk_count_for_a_longer_document():
    # ~900 words at 300/chunk should give exactly 3 chunks.
    text = " ".join(["word"] * 900)
    chunks = chunk_text_by_words(text, words_per_chunk=300)
    assert len(chunks) == 3
    assert sum(c["word_count"] for c in chunks) == 900
