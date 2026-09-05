from app.ai.plagiarism_scoring import DEFAULT_FLAG_THRESHOLD, compute_similarity_scores

# Real-ish, substantial (50+ word) academic-style text — reused/adapted
# across fixtures below the same way this project's other test files use a
# consistent real excerpt, not toy "aaa bbb" strings.

_IOT_PAPER = (
    "Industrial IoT deployments generate high-volume sensor streams that "
    "must be monitored for anomalies in real time. This paper presents a "
    "lightweight detection approach combining a sliding-window statistical "
    "baseline with a small gradient-boosted classifier, evaluated on three "
    "months of production line data from a mid-size manufacturing facility. "
    "Existing anomaly detection approaches often assume cloud connectivity, "
    "which is not always available on factory floors, motivating an "
    "edge-deployable alternative that trades some accuracy for much lower "
    "latency and no dependency on a persistent network connection."
)

# Same paper, copy-pasted verbatim — the clearest possible plagiarism case.
_IOT_PAPER_VERBATIM_COPY = _IOT_PAPER

# Same paper, lightly reworded (synonym swaps, reordered clauses) — the
# realistic "someone edited a few words" resubmission case, not exact copy.
_IOT_PAPER_LIGHTLY_EDITED = (
    "Industrial IoT systems produce high-volume sensor data streams that "
    "need real-time anomaly monitoring. This work introduces a lightweight "
    "detection method that combines a sliding-window statistical baseline "
    "with a compact gradient-boosted classifier, tested on three months of "
    "production-line data from a medium-sized manufacturing plant. Many "
    "existing anomaly detection methods assume cloud connectivity, which "
    "isn't always present on factory floors, which motivates an "
    "edge-deployable alternative trading some accuracy for lower latency "
    "and no reliance on a persistent network connection."
)

# A genuinely unrelated topic and register — plant genetics, not industrial
# IoT — should NOT score as similar despite both being formal academic prose.
_UNRELATED_PAPER = (
    "Drought stress significantly reduces crop yield in arid and semi-arid "
    "agricultural regions worldwide. This study examines the physiological "
    "response of three wheat cultivars to induced water deficit conditions "
    "during the critical grain-filling growth stage. Stomatal conductance, "
    "leaf water potential, and chlorophyll fluorescence were measured at "
    "regular intervals across a twelve-week greenhouse trial. Results "
    "indicate substantial variation in drought tolerance mechanisms between "
    "cultivars, with implications for future breeding programs targeting "
    "climate resilience in staple grain crops."
)

# A second unrelated paper, different topic again, for a three-way
# not-similar-to-anything scenario.
_ANOTHER_UNRELATED_PAPER = (
    "Urban traffic congestion imposes significant economic and "
    "environmental costs in rapidly growing metropolitan areas. This paper "
    "proposes a reinforcement-learning-based traffic signal control system "
    "that adapts to real-time congestion patterns across a network of "
    "interconnected intersections. Simulation results across a downtown "
    "grid layout show meaningful reductions in average commute time "
    "compared to fixed-timing baseline signals, particularly during peak "
    "morning and evening rush-hour periods."
)


def test_verbatim_copy_scores_very_high_and_is_flagged():
    result = compute_similarity_scores(_IOT_PAPER, [{"submission_id": "sub-1", "text": _IOT_PAPER_VERBATIM_COPY}])
    assert result["highest_similarity"] > 0.99  # should be ~1.0 for identical text
    assert len(result["matches"]) == 1
    assert result["matches"][0]["submission_id"] == "sub-1"


def test_lightly_edited_reuse_still_scores_high_and_is_flagged():
    result = compute_similarity_scores(_IOT_PAPER, [{"submission_id": "sub-2", "text": _IOT_PAPER_LIGHTLY_EDITED}])
    assert result["highest_similarity"] > DEFAULT_FLAG_THRESHOLD
    assert len(result["matches"]) == 1


def test_unrelated_paper_scores_low_and_is_not_flagged():
    result = compute_similarity_scores(_IOT_PAPER, [{"submission_id": "sub-3", "text": _UNRELATED_PAPER}])
    assert result["highest_similarity"] < DEFAULT_FLAG_THRESHOLD
    assert result["matches"] == []


def test_multiple_candidates_sorted_by_similarity_descending():
    result = compute_similarity_scores(
        _IOT_PAPER,
        [
            {"submission_id": "unrelated-1", "text": _UNRELATED_PAPER},
            {"submission_id": "verbatim", "text": _IOT_PAPER_VERBATIM_COPY},
            {"submission_id": "unrelated-2", "text": _ANOTHER_UNRELATED_PAPER},
            {"submission_id": "edited", "text": _IOT_PAPER_LIGHTLY_EDITED},
        ],
    )
    assert result["candidates_compared"] == 4
    # Only the two actually-similar ones should be flagged, the unrelated
    # ones should not appear in matches at all.
    matched_ids = [m["submission_id"] for m in result["matches"]]
    assert "verbatim" in matched_ids
    assert "edited" in matched_ids
    assert "unrelated-1" not in matched_ids
    assert "unrelated-2" not in matched_ids
    # Verbatim copy must rank above the lightly-edited version — it's a
    # strictly closer match.
    assert matched_ids[0] == "verbatim"
    assert result["highest_similarity"] > 0.99


def test_empty_candidates_returns_zero_similarity_not_an_error():
    result = compute_similarity_scores(_IOT_PAPER, [])
    assert result["highest_similarity"] == 0.0
    assert result["matches"] == []
    assert result["candidates_compared"] == 0


def test_too_short_submitted_text_raises():
    try:
        compute_similarity_scores("Too short to compare meaningfully.", [{"submission_id": "sub-1", "text": _IOT_PAPER}])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "too short" in str(e).lower()


def test_too_short_candidate_is_skipped_not_compared():
    result = compute_similarity_scores(
        _IOT_PAPER,
        [
            {"submission_id": "sub-1", "text": "A very short candidate text."},
            {"submission_id": "sub-2", "text": _IOT_PAPER_VERBATIM_COPY},
        ],
    )
    assert result["candidates_compared"] == 1
    assert result["candidates_skipped_too_short"] == 1
    assert result["matches"][0]["submission_id"] == "sub-2"


def test_custom_flag_threshold_is_respected():
    # With an artificially high threshold, even the lightly-edited version
    # shouldn't be flagged (though it would be at the default threshold —
    # see test_lightly_edited_reuse_still_scores_high_and_is_flagged).
    result = compute_similarity_scores(
        _IOT_PAPER, [{"submission_id": "sub-1", "text": _IOT_PAPER_LIGHTLY_EDITED}], flag_threshold=0.999
    )
    assert result["matches"] == []
    assert result["highest_similarity"] < 0.999
