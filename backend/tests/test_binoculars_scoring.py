import math

import pytest

from app.ai.binoculars_scoring import (
    binoculars_score,
    compute_cross_perplexity,
    compute_perplexity,
    verdict,
)


# ── compute_perplexity — hand-verifiable examples ──────────────────

def test_perplexity_is_one_for_perfect_prediction():
    # log(1.0) = 0 for every token => perplexity = exp(0) = 1.0 exactly.
    # A model that assigns probability 1.0 to every actual next token is
    # "never surprised" — the textbook-minimum perplexity.
    result = compute_perplexity([math.log(1.0), math.log(1.0), math.log(1.0)])
    assert result == pytest.approx(1.0)


def test_perplexity_is_two_when_every_token_is_50_percent_probable():
    # mean(-log(0.5)) = log(2) => exp(log(2)) = 2.0 exactly.
    result = compute_perplexity([math.log(0.5), math.log(0.5)])
    assert result == pytest.approx(2.0)


def test_perplexity_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        compute_perplexity([])


# ── compute_cross_perplexity — hand-verifiable examples ────────────

def test_cross_perplexity_of_identical_uniform_distributions_equals_vocab_size():
    # A well-known identity: for a UNIFORM distribution over V symbols,
    # entropy = log(V), so perplexity/cross-perplexity = V. Verified here
    # with V=4 as an independent hand-check of the formula, not just an
    # arbitrary example.
    v = 4
    uniform_probs = [1.0 / v] * v
    uniform_logprobs = [math.log(1.0 / v)] * v
    result = compute_cross_perplexity([uniform_probs], [uniform_logprobs])
    assert result == pytest.approx(v)


def test_cross_perplexity_two_positions_matches_hand_calculation():
    # Position 1: performer=[0.5,0.5], observer_log=[log(0.5),log(0.5)]
    #   cross_entropy_1 = -(0.5*log(0.5) + 0.5*log(0.5)) = log(2)
    # Position 2: performer=[1.0,0.0], observer_log=[log(1.0),log(0.0->skip via 0-weight)]
    #   cross_entropy_2 = -(1.0*log(1.0) + 0.0*anything) = 0
    #   (0 * log(anything) term contributes 0 regardless, standard convention)
    performer = [[0.5, 0.5], [1.0, 0.0]]
    observer_log = [[math.log(0.5), math.log(0.5)], [math.log(1.0), math.log(1e-300)]]
    result = compute_cross_perplexity(performer, observer_log)
    mean_cross_entropy = (math.log(2) + 0.0) / 2
    assert result == pytest.approx(math.exp(mean_cross_entropy), rel=1e-6)


def test_cross_perplexity_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        compute_cross_perplexity([], [])


def test_cross_perplexity_rejects_mismatched_position_counts():
    with pytest.raises(ValueError, match="same number of positions"):
        compute_cross_perplexity([[0.5, 0.5]], [[0.5, 0.5], [0.5, 0.5]])


def test_cross_perplexity_rejects_mismatched_vocab_size():
    with pytest.raises(ValueError, match="same vocabulary size"):
        compute_cross_perplexity([[0.5, 0.5]], [[math.log(0.33)] * 3])


# ── binoculars_score — combines both, checks the full shape ────────

def test_binoculars_score_combines_perplexity_and_cross_perplexity_correctly():
    # perplexity=2.0 (from the 50%-probable-token case) over cross-perplexity
    # =2.0 (from the identical-uniform-V=2 case) should give score = 1.0.
    result = binoculars_score(
        observer_token_logprobs=[math.log(0.5), math.log(0.5)],
        performer_next_token_probs=[[0.5, 0.5]],
        observer_next_token_logprobs=[[math.log(0.5), math.log(0.5)]],
    )
    assert result["perplexity"] == pytest.approx(2.0)
    assert result["cross_perplexity"] == pytest.approx(2.0)
    assert result["score"] == pytest.approx(1.0)


def test_binoculars_score_lower_when_models_agree_more_than_text_is_predictable():
    # If the observer finds the text MORE surprising (lower probability on
    # actual tokens => higher perplexity) than the cross-model comparison
    # suggests (models agree with each other => lower cross-perplexity),
    # the ratio goes up. This is the qualitative behavior the method
    # depends on — verified directionally, not just that a number comes out.
    high_ppl_case = binoculars_score(
        observer_token_logprobs=[math.log(0.1), math.log(0.1)],  # observer very surprised by actual tokens
        performer_next_token_probs=[[0.5, 0.5]],
        observer_next_token_logprobs=[[math.log(0.5), math.log(0.5)]],
    )
    low_ppl_case = binoculars_score(
        observer_token_logprobs=[math.log(0.9), math.log(0.9)],  # observer barely surprised
        performer_next_token_probs=[[0.5, 0.5]],
        observer_next_token_logprobs=[[math.log(0.5), math.log(0.5)]],
    )
    assert high_ppl_case["score"] > low_ppl_case["score"]


# ── verdict — boundary behavior ─────────────────────────────────────

def test_verdict_below_threshold_is_likely_ai():
    assert verdict(0.5, threshold=0.9) == "likely_ai"


def test_verdict_above_threshold_is_likely_human():
    assert verdict(0.95, threshold=0.9) == "likely_human"


def test_verdict_exactly_at_threshold_is_likely_human():
    # Boundary is a deliberate design choice (score < threshold, not <=) —
    # locked in via test so it can't silently flip during a refactor.
    assert verdict(0.9, threshold=0.9) == "likely_human"
