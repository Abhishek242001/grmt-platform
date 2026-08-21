"""Grammar check via self-hosted LanguageTool (feature #1 of the 8 AI-driven
checks, per the model inventory — README/planning log §2).

Deterministic, not LLM-based: LanguageTool returns rule-based matches, so the
same document produces the same result every run. This matters for a check
that can feed into an auto-reject gate.
"""
import os
import re

import httpx

from app.core.config import settings

# Chunk size, not a truncation cap — the WHOLE document is checked, split
# into pieces this size so each request stays comfortably under
# LanguageTool's own per-request limits. Previously (planning log §27) this
# was used as a hard truncation point, silently checking only the first
# ~20,000 characters of any document — roughly 2-3 pages of a real paper.
CHUNK_SIZE = 15000
MAX_MATCHES_STORED = 100  # cap what we persist; the score is computed from the full count

# Matches "Abstract" / "ABSTRACT" / "References" / "REFERENCES" only at the
# START of a paragraph (right after \n\n, or the very start of the text) —
# never mid-sentence. This is what makes case-insensitivity safe here: a
# genuine heading is always paragraph-initial; the earlier case-sensitive
# ALL-CAPS-only version (planning log §26) was calibrated against a
# PUBLISHED, typeset article's style, but real manuscript templates
# overwhelmingly use "Abstract" as a title-case RUN-IN heading instead
# ("Abstract — text starts right here on the same line", confirmed against
# a real IEEE manuscript template, planning log §31) — the ALL-CAPS-only
# version missed this entirely on real submission-shaped documents.
_BODY_START_PATTERN = re.compile(r"(?:^|(?<=\n\n))ABSTRACT\b", re.IGNORECASE)
_BODY_END_PATTERN = re.compile(r"(?:^|(?<=\n\n))REFERENCES\b", re.IGNORECASE)
_ACRONYM_LIKE = re.compile(r"[A-Za-z]*[A-Z].*[A-Z]")
_SPELLING_RULE_PREFIX = "MORFOLOGIK_"
_PARA_BREAK = re.compile(r"\n\n")


def _trim_to_body(text: str) -> tuple[str, int, int]:
    """Returns (trimmed_text, start, end) — start/end are the char range of
    the ORIGINAL text that was kept, needed to re-anchor a page_map onto the
    trimmed text. Keeps only Abstract-through-References if those markers
    are found; falls back to the full text (start=0, end=len(text)) otherwise."""
    start_match = _BODY_START_PATTERN.search(text)
    end_match = _BODY_END_PATTERN.search(text, start_match.end() if start_match else 0)

    start = start_match.start() if start_match else 0
    end = end_match.start() if end_match else len(text)

    if end <= start:
        return text, 0, len(text)
    return text[start:end], start, end


def _slice_page_map(page_map, start: int, end: int):
    """Re-anchors a page_map (list of (start,end,page) in ORIGINAL text
    coordinates) onto a [start:end) slice of that text — used after
    _trim_to_body, so page lookups still resolve correctly post-trim."""
    sliced = []
    for p_start, p_end, page_number in page_map:
        new_start = max(p_start, start) - start
        new_end = min(p_end, end) - start
        if new_end > new_start:
            sliced.append((new_start, new_end, page_number))
    return sliced


def _page_for_offset(page_map, offset: int):
    if not page_map:
        return None
    for start, end, page in page_map:
        if start <= offset < end:
            return page
    return None


def _split_into_chunks(text: str, max_chars: int = CHUNK_SIZE):
    """Splits text into (chunk_start_offset, chunk_text) pieces, breaking at
    paragraph boundaries where possible so we don't cut mid-sentence. This is
    what makes full-document checking possible instead of truncating at
    CHUNK_SIZE — every chunk gets its own LanguageTool call, and match
    offsets are translated back to global offsets afterward."""
    if len(text) <= max_chars:
        return [(0, text)]

    boundary_positions = [m.end() for m in _PARA_BREAK.finditer(text)]
    boundary_positions.append(len(text))

    chunks = []
    chunk_start = 0
    last_boundary = 0
    for pos in boundary_positions:
        if pos - chunk_start > max_chars:
            if last_boundary > chunk_start:
                chunks.append((chunk_start, text[chunk_start:last_boundary]))
                chunk_start = last_boundary
            else:
                # a single paragraph itself exceeds max_chars — hard-cut rather than loop forever
                chunks.append((chunk_start, text[chunk_start:chunk_start + max_chars]))
                chunk_start += max_chars
        last_boundary = pos
    if chunk_start < len(text):
        chunks.append((chunk_start, text[chunk_start:]))
    return chunks


def extract_text_from_docx(file_path: str) -> str:
    from app.ai.docx_utils import open_docx

    doc = open_docx(file_path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_text(file_path: str):
    """Dispatches by extension. Returns (text, page_map) — page_map is None
    for .docx (no fixed page concept without rendering), or a real list of
    (start, end, page_number) spans for .pdf."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return extract_text_from_docx(file_path), None
    elif ext == ".pdf":
        from app.ai.pdf_text_extraction import extract_text_from_pdf
        return extract_text_from_pdf(file_path)
    else:
        raise ValueError(f"Unsupported file type for text extraction: {ext}")


def run_grammar_check(file_path: str) -> dict:
    """Returns a dict always shaped the same way, whether it succeeds or fails,
    so callers never have to branch on a missing key."""
    try:
        raw_text, page_map = extract_text(file_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}", "matches": [], "error_count": 0, "score": None}

    if not raw_text.strip():
        return {"status": "error", "error": "No extractable text found in document", "matches": [], "error_count": 0, "score": None}

    text, trim_start, trim_end = _trim_to_body(raw_text)
    sliced_page_map = _slice_page_map(page_map, trim_start, trim_end) if page_map else None

    chunks = _split_into_chunks(text)
    all_matches = []
    chunks_failed = 0

    for chunk_start, chunk_text in chunks:
        try:
            resp = httpx.post(
                settings.languagetool_url,
                data={"text": chunk_text, "language": "en-US"},
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            chunks_failed += 1
            continue

        for m in data.get("matches", []):
            local_offset = m.get("offset", 0)
            length = m.get("length", 0)
            flagged_word = chunk_text[local_offset:local_offset + length]
            rule_id = (m.get("rule") or {}).get("id", "")
            if rule_id.startswith(_SPELLING_RULE_PREFIX) and _ACRONYM_LIKE.search(flagged_word):
                continue  # e.g. "AIoT", "IoT", "PdM" — technical acronym, not a real typo

            global_offset = chunk_start + local_offset
            all_matches.append({
                "message": m.get("message"),
                "short_message": m.get("shortMessage"),
                "offset": global_offset,
                "length": length,
                "rule_id": rule_id,
                "category": ((m.get("rule") or {}).get("category") or {}).get("name"),
                "page": _page_for_offset(sliced_page_map, global_offset),
            })

    if chunks and chunks_failed == len(chunks):
        return {"status": "error", "error": "LanguageTool request failed for all chunks", "matches": [], "error_count": 0, "score": None}

    error_count = len(all_matches)
    word_count = max(len(text.split()), 1)
    errors_per_100_words = (error_count / word_count) * 100
    score = max(0.0, round(100 - errors_per_100_words * 5, 1))

    return {
        "status": "complete",
        "error_count": error_count,
        "word_count": word_count,
        "score": score,
        "chunks_checked": len(chunks) - chunks_failed,
        "chunks_total": len(chunks),
        "matches": all_matches[:MAX_MATCHES_STORED],
    }
