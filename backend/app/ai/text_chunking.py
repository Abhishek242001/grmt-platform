"""Splits extracted document text into word-count-based chunks — the
"bucket" step of the AI-content-detection pipeline (get text -> chunk into
buckets -> score each bucket -> average -> threshold -> highlight flagged
buckets). Zero model dependency, fully unit-testable.

Word-count chunking (not sentence-aware) deliberately, to match the
pipeline spec directly: chunk on a target word count, not on sentence/
paragraph boundaries. A chunk can end mid-sentence. This is simpler and
more predictable than sentence-aware chunking, and avoids adding a
sentence-tokenizer dependency (NLTK/spaCy) for a first version — worth
revisiting if per-chunk scores near a chunk boundary turn out to be
noisier than mid-chunk scores in practice, but that's a real-data
question, not something to guess at upfront.
"""
import re

# 200-500 words was the range given in the pipeline spec (per-instance
# "bucket" size); 300 is the chosen default — comfortably fits BERT-base's
# 512-token limit (English averages ~1.3 wordpiece tokens per word, so
# ~300 words is ~390 tokens, leaving headroom for [CLS]/[SEP] and the
# occasional longer word) while still being close to the upper end of
# the requested range, not the conservative low end.
DEFAULT_WORDS_PER_CHUNK = 300


def chunk_text_by_words(text: str, words_per_chunk: int = DEFAULT_WORDS_PER_CHUNK) -> list[dict]:
    """Returns a list of chunks, each a dict with:
        text: the chunk's own text (whitespace-joined, not the original
              raw slice — see note below)
        start_char: index into the ORIGINAL text where this chunk's first
              word begins
        end_char: index into the ORIGINAL text where this chunk's last
              word ends
        word_count: number of words in this chunk

    start_char/end_char point into the original text (not the chunk's own
    re-joined text) so a caller can highlight the exact original span,
    including any original whitespace/formatting between words — this
    matters for a future "highlight this passage in the document" UI
    feature, not just for scoring.

    Raises ValueError for empty/whitespace-only input or a non-positive
    words_per_chunk — both would otherwise silently produce a nonsensical
    result (zero chunks, or an infinite/zero-size chunking loop)."""
    if words_per_chunk <= 0:
        raise ValueError("words_per_chunk must be positive")
    if not text.strip():
        raise ValueError("text must not be empty")

    # re.finditer with \S+ gives exact character spans for each word,
    # which a naive text.split() throws away — needed for start_char/end_char.
    word_matches = list(re.finditer(r"\S+", text))
    if not word_matches:
        raise ValueError("text must not be empty")

    chunks = []
    for i in range(0, len(word_matches), words_per_chunk):
        group = word_matches[i:i + words_per_chunk]
        start_char = group[0].start()
        end_char = group[-1].end()
        chunk_text = text[start_char:end_char]
        chunks.append({
            "text": chunk_text,
            "start_char": start_char,
            "end_char": end_char,
            "word_count": len(group),
        })

    return chunks
