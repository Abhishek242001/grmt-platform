"""The full AI-content-detection pipeline, matching the organizer's actual
policy model: get text -> chunk into buckets -> score each bucket -> compute
what PERCENTAGE OF THE DOCUMENT'S WORDS fall in AI-flagged buckets -> compare
against an organizer-configured maximum (e.g. "must be under 15% AI-generated
content") -> highlight the flagged buckets.

Word-weighted, not a simple average of per-chunk probabilities — this was a
real design correction, not an refinement of the original approach. A plain
average treats every chunk as equally important regardless of how many words
it actually represents, which doesn't correspond to an organizer's "under
15% of the content" policy at all: a tiny 10-word flagged chunk and a
200-word flagged chunk would move a simple average by the same amount, but
they represent very different fractions of the actual document. Word-
weighting fixes this directly: percentage = (words in AI-flagged chunks) /
(total words) * 100, which is literally what "15% AI-generated content"
means as a policy statement.

Split into a pure aggregation layer (aggregate_chunk_results — zero model
dependency, fully unit-tested with hand-verifiable examples) and an
orchestrator (run_pipeline) that wires extraction -> chunking -> per-chunk
scoring -> aggregation together. The scorer is INJECTABLE — defaults to
followsci_check's model (the only one of the four approaches tried so far
that didn't show a bias against formal academic writing — see
PROJECT_HANDOFF.md's decision record), but any function with the same
signature (str -> {"ai_probability": float}) can be passed in instead, so
swapping to a fine-tuned model later is a one-line change here, not a
rewrite of the chunking/aggregation/highlighting logic.
"""
import os

from app.ai.grammar_check import extract_text
from app.ai.text_chunking import DEFAULT_WORDS_PER_CHUNK, chunk_text_by_words

# The per-chunk probability threshold — decides whether an individual
# chunk COUNTS TOWARD the AI-word-total at all. Distinct from
# max_ai_percentage below, which is the organizer's overall policy number.
DEFAULT_CHUNK_PROBABILITY_THRESHOLD = 0.5

# The organizer-configured policy threshold, e.g. 15.0 for "must be under
# 15% AI-generated content." On a 0-100 scale to match the convention every
# other check in this project already uses (format/table_figure's score
# field), so this can plug into the same GateRule system — BUT the pass/
# fail comparison direction is INVERTED from those checks: format/
# table_figure pass when score >= threshold (higher is better — more
# checks passed). This one passes when percentage < threshold (lower is
# better — less AI-generated content). Whoever wires this into
# gate_engine.py's CHECK_EVALUATORS must NOT copy the existing >=
# comparison pattern — that would silently accept everything except a
# 100%-AI-generated submission.
DEFAULT_MAX_AI_PERCENTAGE = 15.0


def aggregate_chunk_results(
    chunks: list[dict],
    chunk_probability_threshold: float = DEFAULT_CHUNK_PROBABILITY_THRESHOLD,
    max_ai_percentage: float = DEFAULT_MAX_AI_PERCENTAGE,
) -> dict:
    """Pure aggregation — no model calls, no I/O.

    chunks: list of dicts, each must have "word_count" (int) and
    "ai_probability" (float) — typically chunk_text_by_words()'s output
    with "ai_probability" added after scoring each chunk's text.

    A chunk counts toward the AI-word-total only if its OWN probability
    exceeds chunk_probability_threshold — this is what makes the result
    word-weighted rather than a flat average: chunks aren't all treated
    as equally significant, their actual size determines how much they
    move the final percentage.

    "Must have less than 15%" — accept requires percentage STRICTLY below
    max_ai_percentage; exactly at the threshold fails, matching how the
    policy was actually stated (a document at exactly 15% does not meet
    "must be less than 15%")."""
    if not chunks:
        raise ValueError("chunks must not be empty")

    total_words = sum(c["word_count"] for c in chunks)
    if total_words == 0:
        raise ValueError("total word count must be greater than zero")

    flagged_indices = [i for i, c in enumerate(chunks) if c["ai_probability"] > chunk_probability_threshold]
    ai_word_count = sum(chunks[i]["word_count"] for i in flagged_indices)
    ai_generated_percentage = (ai_word_count / total_words) * 100

    overall_verdict = "reject" if ai_generated_percentage >= max_ai_percentage else "accept"

    return {
        "ai_generated_percentage": ai_generated_percentage,
        "ai_word_count": ai_word_count,
        "total_word_count": total_words,
        "flagged_chunk_indices": flagged_indices,
        "flagged_chunk_count": len(flagged_indices),
        "total_chunk_count": len(chunks),
        "overall_verdict": overall_verdict,
        "max_ai_percentage": max_ai_percentage,
    }


def run_pipeline(
    file_path: str,
    words_per_chunk: int = DEFAULT_WORDS_PER_CHUNK,
    chunk_probability_threshold: float = DEFAULT_CHUNK_PROBABILITY_THRESHOLD,
    max_ai_percentage: float = DEFAULT_MAX_AI_PERCENTAGE,
    scorer=None,
    pdf_path_for_highlighting: str | None = None,
) -> dict:
    """The real orchestrator. `scorer` defaults to followsci_check's model
    (lazy-imported here, not at module level, so this file stays importable
    without torch installed, and so tests can inject a mock scorer instead
    of needing a real GPU). Any callable matching
    `str -> {"ai_probability": float}` can be passed instead.

    `pdf_path_for_highlighting` (update41): a real PDF to compute bounding
    boxes against, separate from `file_path` — text is always extracted
    from `file_path` itself (matching the original document exactly, which
    matters for .docx since extract_text's .docx path reads paragraph text
    directly, not through a lossy PDF round-trip), but bounding-box search
    needs an actual rendered PDF page to search text on. For a native .pdf
    upload these are usually the same file; for .docx, pass the already-
    converted PDF (see submissions.py's converted_pdf_path) so .docx
    submissions get real highlighting too, not just native PDF uploads.
    None (the default) skips highlighting entirely — every flagged chunk
    still gets an empty "highlight_boxes": [] rather than a missing key."""
    if scorer is None:
        from app.ai.followsci_check import _score_text as scorer

    # Prefer extracting from the real PDF when one's available, not the
    # original file_path — this matters specifically for .docx: extract_text
    # never returns a page_map for .docx (no fixed page concept without
    # rendering), so scoring against the .docx directly would make
    # highlighting permanently impossible for every .docx submission,
    # regardless of pdf_path_for_highlighting being given. Extracting from
    # the SAME PDF that highlighting will search keeps chunk boundaries and
    # page_map internally consistent (searching for a chunk's exact text on
    # the exact page it was extracted from). Trade-off, stated plainly: for
    # a .docx with a successful conversion, scoring now runs against the
    # PDF's column-aware extraction (pdf_text_extraction.py) rather than
    # the .docx's direct paragraph text — these can differ slightly (minor
    # whitespace/formatting from the conversion round-trip). Given the
    # alternative is .docx submissions never getting highlighting at all,
    # and citation_check.py already fully commits to the converted PDF over
    # the original .docx with no such hedging, this is the same call this
    # project has already made elsewhere, not a new precedent.
    extraction_path = file_path
    if pdf_path_for_highlighting and os.path.splitext(pdf_path_for_highlighting)[1].lower() == ".pdf":
        extraction_path = pdf_path_for_highlighting

    try:
        text, page_map = extract_text(extraction_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}"}

    if not text.strip():
        return {"status": "error", "error": "No extractable text found in document"}

    try:
        chunks = chunk_text_by_words(text, words_per_chunk=words_per_chunk)
    except ValueError as e:
        return {"status": "error", "error": f"Chunking failed: {e}"}

    try:
        for chunk in chunks:
            chunk["ai_probability"] = scorer(chunk["text"])["ai_probability"]
    except Exception as e:
        return {"status": "error", "error": f"Scoring failed: {e}"}

    aggregation = aggregate_chunk_results(
        chunks, chunk_probability_threshold=chunk_probability_threshold, max_ai_percentage=max_ai_percentage
    )

    # Attach the actual chunk text/spans to the flagged indices, so a caller
    # (eventually the frontend) can highlight the exact passages, not just
    # know that "chunk 3 was flagged" with no way to show the user which
    # text that refers to.
    flagged_chunks = [
        {
            "text": chunks[i]["text"],
            "start_char": chunks[i]["start_char"],
            "end_char": chunks[i]["end_char"],
            "word_count": chunks[i]["word_count"],
            "ai_probability": chunks[i]["ai_probability"],
        }
        for i in aggregation["flagged_chunk_indices"]
    ]

    # update41: real page-anchored bounding boxes, when a PDF is available.
    # Only attempted for .pdf text extraction (page_map is real) with a real
    # PDF path given — .docx with no converted PDF, or extraction that
    # returned no page_map for any other reason, degrades gracefully to an
    # empty highlight_boxes list per chunk rather than erroring the whole
    # check over a feature that's inherently best-effort (see
    # ai_text_highlighting.py's own docstring on match-rate limitations).
    if pdf_path_for_highlighting and page_map:
        try:
            from app.ai.ai_text_highlighting import compute_highlight_boxes

            flagged_chunks = compute_highlight_boxes(pdf_path_for_highlighting, flagged_chunks, page_map)
        except Exception:
            # Highlighting is a bonus on top of the actual detection result
            # — a failure here (corrupt PDF, PyMuPDF error) must not take
            # down the whole AI-text check. Fall back to empty boxes.
            flagged_chunks = [{**c, "highlight_boxes": []} for c in flagged_chunks]
    else:
        flagged_chunks = [{**c, "highlight_boxes": []} for c in flagged_chunks]

    return {
        "status": "complete",
        "ai_generated_percentage": aggregation["ai_generated_percentage"],
        "ai_word_count": aggregation["ai_word_count"],
        "total_word_count": aggregation["total_word_count"],
        "overall_verdict": aggregation["overall_verdict"],
        "total_chunk_count": aggregation["total_chunk_count"],
        "flagged_chunk_count": aggregation["flagged_chunk_count"],
        "flagged_chunks": flagged_chunks,
        "chunk_probability_threshold": chunk_probability_threshold,
        "max_ai_percentage": max_ai_percentage,
    }


def run_ai_text_detection_check(file_path: str, pdf_path_for_highlighting: str | None = None) -> dict:
    """Thin naming-convention alias for run_pipeline() — every other check
    in this project is called via run_<check_type>_check(file_path)
    (run_grammar_check, run_format_compliance_check, run_table_figure_check),
    and submissions.py's checks_to_run loop expects that shape. Uses every
    default (300 words/chunk, 0.5 per-chunk probability threshold, 15.0%
    max — see this module's constants) since the check itself computes the
    raw fact (ai_generated_percentage); the actual gate PASS/FAIL decision
    against the organizer's real configured threshold happens separately
    in gate_engine.py's _ai_text_passes, not here — same separation of
    concerns as every other check."""
    return run_pipeline(file_path, pdf_path_for_highlighting=pdf_path_for_highlighting)


def run_manual_verification():
    """Real end-to-end run on a real (temporary) .docx, using the REAL
    followsci model — not mocked. Builds a document that's roughly half
    genuinely human-written text (the same real excerpt used in every
    prior calibration test) and half genuinely Claude-written text,
    concatenated, so the chunking/highlighting can be checked against
    content whose true origin is actually known per-section. Run with:
        python3 -c "from app.ai.ai_content_pipeline import run_manual_verification as r; r()"
    """
    import os
    import tempfile

    from docx import Document

    human_part = (
        "Industrial IoT deployments generate high-volume sensor streams that "
        "must be monitored for anomalies in real time. This paper presents a "
        "lightweight detection approach combining a sliding-window statistical "
        "baseline with a small gradient-boosted classifier, evaluated on three "
        "months of production line data from a mid-size manufacturing facility. "
        "Existing anomaly detection approaches often assume cloud connectivity, "
        "which is not always available on factory floors. "
    ) * 4  # repeated to comfortably exceed one chunk's worth of words on its own

    ai_part = (
        "The proliferation of edge computing architectures has fundamentally "
        "transformed the landscape of real-time data processing in industrial "
        "environments. By leveraging distributed sensor networks in conjunction "
        "with lightweight machine learning models, organizations can achieve "
        "significant improvements in operational efficiency while simultaneously "
        "reducing the latency associated with traditional cloud-based analytics. "
    ) * 4

    full_text = human_part + ai_part

    doc = Document()
    doc.add_paragraph(full_text)
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, "verification.docx")
    doc.save(path)

    print(f"Test document: {len(full_text.split())} words, roughly first half "
          f"real human text, second half genuinely Claude-written.\n")

    result = run_pipeline(path)

    print(f"Status: {result['status']}")
    if result["status"] != "complete":
        print(f"Error: {result.get('error')}")
        return

    print(f"Total chunks: {result['total_chunk_count']}")
    print(f"AI-generated percentage: {result['ai_generated_percentage']:.2f}% "
          f"({result['ai_word_count']}/{result['total_word_count']} words)")
    print(f"Max allowed (organizer policy): {result['max_ai_percentage']}%")
    print(f"Overall verdict: {result['overall_verdict']}")
    print(f"Flagged chunks: {result['flagged_chunk_count']}")
    for i, chunk in enumerate(result["flagged_chunks"], 1):
        preview = chunk["text"][:80].replace("\n", " ")
        print(f"  [{i}] ai_probability={chunk['ai_probability']:.4f} ({chunk['word_count']} words) — \"{preview}...\"")

    print(
        "\nWhat to check: the document is roughly half human, half AI content, "
        "in that order. Do the flagged chunks correspond to the SECOND half of "
        "the document (the genuinely-AI part), or is the flagging scattered "
        "without regard to which half is which? That's the real test of "
        "whether chunk-level highlighting will be trustworthy in practice, "
        "not just whether SOME chunks get flagged."
    )
