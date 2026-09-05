"""PDF text extraction — column-aware, since IEEE/Springer papers are almost
always two-column layouts. Naive extraction (raw reading order from PyMuPDF's
default text mode) frequently jumbles lines between columns on this kind of
layout, which would feed grammar/AI checks garbled, out-of-order text —
actively worse than not checking at all.

Approach: bucket each text block by which half of the page its left edge
falls in (left column vs right column), sort blocks within each bucket
top-to-bottom, then emit left column before right column, per page. This is
a heuristic, not a perfect layout parser — full-width blocks (title,
abstract, section headers spanning both columns) will land in whichever half
their left edge happens to fall in, which is usually the left half and
usually reads fine, but isn't guaranteed for every paper's layout.
"""
import re

import pymupdf

# A word broken across a line-wrap inside a justified column looks like
# "com-\nputing" in PyMuPDF's raw block text. Left uncleaned, this produces
# two garbage tokens ("com-" and "puting") that a grammar checker correctly
# but uselessly flags as malformed. Rejoin them.
_HYPHEN_LINE_WRAP = re.compile(r"-\n")


def _clean_block_text(text: str) -> str:
    text = _HYPHEN_LINE_WRAP.sub("", text)  # "com-\nputing" -> "computing"
    text = text.replace("\n", " ")
    return re.sub(r" {2,}", " ", text).strip()


def extract_text_from_pdf(file_path: str) -> tuple[str, list[tuple[int, int, int]]]:
    """Returns (text, page_map). page_map is a list of (start_offset,
    end_offset, page_number) spans — 1-indexed pages — covering `text`, so
    any character offset within `text` can be resolved back to the PDF page
    it came from."""
    doc = pymupdf.open(file_path)
    text = ""
    page_map: list[tuple[int, int, int]] = []

    for page_index, page in enumerate(doc):
        page_number = page_index + 1
        blocks = page.get_text("blocks")  # each: (x0, y0, x1, y1, text, block_no, block_type)
        text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]  # type 0 = text block
        if not text_blocks:
            continue

        page_width = page.rect.width
        midpoint = page_width / 2
        left_column = sorted([b for b in text_blocks if b[0] < midpoint], key=lambda b: b[1])
        right_column = sorted([b for b in text_blocks if b[0] >= midpoint], key=lambda b: b[1])

        cleaned_blocks = [c for c in (_clean_block_text(b[4]) for b in left_column + right_column) if c]
        if not cleaned_blocks:
            continue

        page_text = "\n\n".join(cleaned_blocks)
        page_start = len(text)
        if text:
            text += "\n\n"
            page_start = len(text)
        text += page_text
        page_map.append((page_start, len(text), page_number))

    doc.close()
    return text, page_map
