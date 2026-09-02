"""Maps AI-content-detection's flagged chunks to real bounding boxes on the
rendered PDF page, so the frontend can highlight the actual flagged passage
instead of only listing it as text (update41).

Split into a pure layer (page resolution, search-window splitting — zero
PyMuPDF dependency, fully unit-tested without a GPU/PDF library) and an
orchestrator (compute_highlight_boxes) that does the actual PyMuPDF calls —
mirroring this project's own established pattern (e.g. binoculars_scoring.py
vs ai_text_detection_check.py, aggregate_chunk_results vs run_pipeline).

IMPORTANT — genuinely unverified end-to-end: PyMuPDF is not installable in
the environment this was written in (no network access — see the
conversation this was built in). The pure logic below (page resolution,
sentence splitting, percentage conversion) is independently testable and
tested. What is NOT verified here is the real search_for() match rate
against genuine PDF text — see the "why search per-sentence, not per-chunk"
note on _split_into_search_windows for the specific, real risk this is
designed around, and compute_highlight_boxes's docstring for what a real
run needs to confirm.
"""
import re

# A flagged chunk is ~300 words — searching for that whole block verbatim
# via PyMuPDF's search_for() will very likely never match. Two real reasons,
# both confirmed in pdf_text_extraction.py's own text-cleaning step:
#   1. De-hyphenation: "com-\nputing" (the PDF's actual line-wrapped
#      rendering) becomes "computing" in the extracted text — that
#      contiguous string doesn't exist anywhere in the PDF's real glyph
#      layout, so searching for it (or any surrounding text containing it)
#      fails.
#   2. Separate text BLOCKS get joined with "\n\n" in the extracted text,
#      but that join is an artifact of extraction, not a real blank line in
#      the PDF — text spanning a block boundary won't match as one string.
# Splitting into individual sentences shrinks each search string enough that
# a given window has good odds of NOT crossing a hyphenation point or block
# boundary, and a handful of missed windows (whichever ones do cross one)
# still leaves most of the chunk's real bounding boxes recoverable — this
# is deliberately a best-effort match, not a completeness guarantee.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# A window shorter than this is too generic to search for reliably — e.g.
# "Fig. 1." or "et al." could match dozens of places on a page that have
# nothing to do with the actually-flagged passage. Skip searching for
# fragments this short rather than risk highlighting the wrong text.
_MIN_SEARCH_WINDOW_CHARS = 15


def split_into_search_windows(chunk_text: str) -> list[str]:
    """Splits a flagged chunk's text into sentence-level windows to search
    for individually, since the whole chunk will very likely never match
    verbatim (see module docstring). Returns only windows long enough to
    search meaningfully — see _MIN_SEARCH_WINDOW_CHARS."""
    windows = [w.strip() for w in _SENTENCE_SPLIT.split(chunk_text)]
    return [w for w in windows if len(w) >= _MIN_SEARCH_WINDOW_CHARS]


def resolve_chunk_pages(page_map: list[tuple[int, int, int]], start_char: int, end_char: int) -> list[int]:
    """Returns every page number a [start_char, end_char) span overlaps —
    usually one page, but a ~300-word chunk can genuinely straddle a page
    boundary, and a chunk landing exactly on a boundary shouldn't silently
    lose whichever half falls on the second page. Returns [] if page_map is
    empty/None (no PDF page info available — e.g. a .docx with no converted
    PDF) or the span doesn't overlap any known page (shouldn't happen for a
    valid page_map, but a caller shouldn't crash if it does)."""
    if not page_map:
        return []
    pages = []
    for p_start, p_end, page_number in page_map:
        if p_start < end_char and p_end > start_char:  # any overlap, not just full containment
            pages.append(page_number)
    return pages


def rect_to_percentage(x0: float, y0: float, x1: float, y1: float, page_width: float, page_height: float) -> dict:
    """Converts a PyMuPDF Rect's point-coordinates (x0,y0,x1,y1) into the
    percentage-of-page convention this project's PdfAnnotation viewer
    already uses elsewhere (xPct/yPct — see PdfAnnotationViewer.tsx),
    rather than inventing a new coordinate convention for this feature.
    PyMuPDF's page coordinate origin is top-left with y increasing
    downward, matching the same top-left-origin convention the frontend
    already assumes for xPct/yPct — no axis flip needed."""
    if page_width <= 0 or page_height <= 0:
        raise ValueError("page_width and page_height must be positive")
    return {
        "xPct": round((x0 / page_width) * 100, 2),
        "yPct": round((y0 / page_height) * 100, 2),
        "wPct": round(((x1 - x0) / page_width) * 100, 2),
        "hPct": round(((y1 - y0) / page_height) * 100, 2),
    }


def compute_highlight_boxes(pdf_path: str, flagged_chunks: list[dict], page_map: list[tuple[int, int, int]]) -> list[dict]:
    """Real orchestrator — for each flagged chunk, finds which page(s) it's
    on via page_map, splits its text into search windows, and searches for
    each window on those pages via PyMuPDF's search_for(). Returns each
    flagged chunk's own dict with a "highlight_boxes" key added: a list of
    {"page": int, "boxes": [{"xPct","yPct","wPct","hPct"}, ...]}, one entry
    per page the chunk's matched windows were found on (a chunk spanning a
    page boundary can have entries for more than one page). A chunk whose
    windows don't match anywhere (or that has no page_map at all — e.g. a
    .docx with no converted PDF) gets an empty "highlight_boxes": [] rather
    than being dropped from the result.

    GENUINELY UNVERIFIED (see module docstring) — PyMuPDF is not available
    in the environment this was written in. Before trusting this against
    real submissions, a real run needs to confirm: (1) search_for() actually
    finds a reasonable fraction of sentence-level windows on real IEEE-
    formatted two-column PDFs, not close to zero, and (2) the resulting
    boxes visually land on the correct passage when rendered, not offset
    or on the wrong page. Run the counterpart in ai_content_pipeline.py's
    run_manual_verification()-style scripts on a real GPU+PDF Studio."""
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        result = []
        for chunk in flagged_chunks:
            pages = resolve_chunk_pages(page_map, chunk["start_char"], chunk["end_char"])
            windows = split_into_search_windows(chunk["text"])

            highlight_boxes = []
            for page_number in pages:
                if page_number < 1 or page_number > len(doc):
                    continue  # a stale/mismatched page_map shouldn't crash the whole check
                page = doc[page_number - 1]  # PyMuPDF is 0-indexed; page_map is 1-indexed
                boxes = []
                for window in windows:
                    for rect in page.search_for(window):
                        boxes.append(rect_to_percentage(rect.x0, rect.y0, rect.x1, rect.y1, page.rect.width, page.rect.height))
                if boxes:
                    highlight_boxes.append({"page": page_number, "boxes": boxes})

            result.append({**chunk, "highlight_boxes": highlight_boxes})
        return result
    finally:
        doc.close()
