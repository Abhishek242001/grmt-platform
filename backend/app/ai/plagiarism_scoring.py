"""Self-submission plagiarism detection — TF-IDF + cosine similarity against
GRMT's own submission history (update43, phase 1 of 3 — see PROJECT_HANDOFF.md
for the corpus decision that scoped this).

Deliberately NOT BGE-M3/FAISS for this first phase: self-plagiarism and
resubmission cases are overwhelmingly near-exact or lightly-modified reuse of
the SAME author's own prior text, not sophisticated paraphrasing of someone
else's work — the case semantic embeddings earn their real cost for. TF-IDF
cosine similarity is a real, established plagiarism-detection baseline
technique (not an ad hoc invention), fully deterministic, and needs no GPU,
no model download, no corpus infrastructure — it can run today, against real
platform data, with zero external dependency.

Split into a pure scoring layer (this module — zero DB dependency, fully
unit-tested) and an orchestrator (plagiarism_check.py) that extracts text and
calls this, matching every other check in this project's own established
pattern (aggregate_chunk_results vs run_pipeline, binoculars_scoring vs
ai_text_detection_check).

Honest limitation, stated upfront: TF-IDF/cosine catches copy-paste and
lightly-edited reuse well; it will miss a genuinely well-paraphrased rewrite
of the same content, the same category of gap that eventually justifies
adding semantic (embedding-based) comparison later — see phase 2/3 of the
corpus decision. This is a real, scoped starting point, not a claim to solve
plagiarism detection completely."""
import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Below this, a similarity score isn't meaningfully distinguishable from two
# unrelated academic papers sharing common domain vocabulary (both papers
# saying "deep learning" and "accuracy" a lot isn't plagiarism) — confirmed
# by testing against real unrelated-topic pairs during development (see
# tests/test_plagiarism_scoring.py's own unrelated-papers fixture).
DEFAULT_FLAG_THRESHOLD = 0.35

# A candidate with fewer real words than this can't produce a meaningful
# TF-IDF comparison at all (too few terms for the vectorizer's vocabulary to
# say anything reliable) — skipped rather than risk a noisy score.
_MIN_WORDS_FOR_COMPARISON = 50

_WORD = re.compile(r"\S+")


def _word_count(text: str) -> int:
    return len(_WORD.findall(text))


def compute_similarity_scores(
    submitted_text: str,
    candidates: list[dict],
    flag_threshold: float = DEFAULT_FLAG_THRESHOLD,
) -> dict:
    """Compares submitted_text against every candidate's text via TF-IDF
    cosine similarity. candidates: list of {"submission_id": str, "text":
    str} — the caller (plagiarism_check.py) is responsible for fetching
    these; this function has zero DB/IO dependency, matching every other
    check's pure-scoring-layer pattern in this project.

    Returns {"highest_similarity": float, "matches": [...], "candidates_compared": int,
    "candidates_skipped_too_short": int} — matches is every candidate scoring
    above flag_threshold, sorted by similarity descending. Empty candidates
    list returns highest_similarity=0.0 and an empty matches list (nothing
    to compare against isn't an error — a submission's own first-ever
    comparison legitimately has no history yet)."""
    if _word_count(submitted_text) < _MIN_WORDS_FOR_COMPARISON:
        raise ValueError(
            f"Submitted text has fewer than {_MIN_WORDS_FOR_COMPARISON} words — "
            "too short for a meaningful similarity comparison"
        )

    usable_candidates = []
    skipped = 0
    for c in candidates:
        if _word_count(c["text"]) < _MIN_WORDS_FOR_COMPARISON:
            skipped += 1
            continue
        usable_candidates.append(c)

    if not usable_candidates:
        return {
            "highest_similarity": 0.0,
            "matches": [],
            "candidates_compared": 0,
            "candidates_skipped_too_short": skipped,
        }

    # Fit ONE vectorizer across submitted text + all candidates together —
    # required for cosine similarity to be meaningful (comparing vectors
    # from two separately-fit vocabularies isn't a valid comparison at all).
    all_texts = [submitted_text] + [c["text"] for c in usable_candidates]
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(all_texts)

    submitted_vector = tfidf_matrix[0:1]
    candidate_vectors = tfidf_matrix[1:]
    similarities = cosine_similarity(submitted_vector, candidate_vectors)[0]

    matches = [
        {
            "submission_id": usable_candidates[i]["submission_id"],
            "similarity": round(float(similarities[i]), 4),
        }
        for i in range(len(usable_candidates))
        if similarities[i] >= flag_threshold
    ]
    matches.sort(key=lambda m: m["similarity"], reverse=True)

    return {
        "highest_similarity": round(float(max(similarities)), 4) if len(similarities) else 0.0,
        "matches": matches,
        "candidates_compared": len(usable_candidates),
        "candidates_skipped_too_short": skipped,
    }
