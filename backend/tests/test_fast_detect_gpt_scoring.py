import math

import pytest

from app.ai.fast_detect_gpt_scoring import (
    compute_curvature,
    distribution_mean_and_variance,
    verdict,
)


# ── distribution_mean_and_variance — hand-verifiable examples ──────

def test_mean_and_variance_of_uniform_distribution_is_log_v_and_zero():
    # Every outcome in a uniform distribution over V symbols has the exact
    # same log-prob (log(1/V)), so the "spread" of possible log-prob values
    # is zero by definition — a clean, exact test of the variance formula,
    # not just an arbitrary example.
    v = 4
    probs = [1.0 / v] * v
    logprobs = [math.log(1.0 / v)] * v
    mean, variance = distribution_mean_and_variance(probs, logprobs)
    assert mean == pytest.approx(math.log(1.0 / v))
    assert variance == pytest.approx(0.0, abs=1e-12)


def test_mean_and_variance_matches_hand_calculation():
    # p=[0.8, 0.2] — computed independently by hand (see conversation this
    # was built in) and cross-checked with a standalone script before being
    # hard-coded here, not derived from the function under test itself.
    probs = [0.8, 0.2]
    logprobs = [math.log(0.8), math.log(0.2)]
    mean, variance = distribution_mean_and_variance(probs, logprobs)
    assert mean == pytest.approx(-0.5004024235381879)
    assert variance == pytest.approx(0.3074899289076488)


def test_mean_and_variance_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        distribution_mean_and_variance([0.5, 0.5], [math.log(0.5)])


def test_mean_and_variance_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        distribution_mean_and_variance([], [])


# ── compute_curvature — hand-verifiable examples ────────────────────

def test_curvature_matches_hand_calculation_single_position():
    # Same p=[0.8, 0.2] distribution; actual observed token is the
    # 0.8-probability one. Hand-calculated (and cross-checked) curvature
    # for this single position is ~0.5 exactly.
    mean, variance = distribution_mean_and_variance([0.8, 0.2], [math.log(0.8), math.log(0.2)])
    result = compute_curvature(
        actual_token_logprobs=[math.log(0.8)],
        self_distribution_means=[mean],
        self_distribution_variances=[variance],
    )
    assert result["curvature"] == pytest.approx(0.5, rel=1e-6)


def test_curvature_is_zero_when_actual_logprob_equals_expected():
    # If the observed text's log-prob exactly matches what the model
    # "expects" on average, the numerator is zero regardless of variance —
    # curvature should be exactly 0.
    result = compute_curvature(
        actual_token_logprobs=[-0.5, -0.5],
        self_distribution_means=[-0.5, -0.5],
        self_distribution_variances=[0.3, 0.3],
    )
    assert result["curvature"] == pytest.approx(0.0, abs=1e-12)


def test_curvature_is_positive_when_text_more_probable_than_expected():
    # actual log-prob (-0.1, high probability) is LESS negative than the
    # expected mean (-0.5) — text is more probable than "typical" for this
    # model, which is exactly the AI-generated signature Fast-DetectGPT
    # looks for. Curvature should come out positive.
    result = compute_curvature(
        actual_token_logprobs=[-0.1, -0.1],
        self_distribution_means=[-0.5, -0.5],
        self_distribution_variances=[0.3, 0.3],
    )
    assert result["curvature"] > 0


def test_curvature_is_negative_when_text_less_probable_than_expected():
    result = compute_curvature(
        actual_token_logprobs=[-0.9, -0.9],
        self_distribution_means=[-0.5, -0.5],
        self_distribution_variances=[0.3, 0.3],
    )
    assert result["curvature"] < 0


def test_curvature_rejects_zero_total_variance():
    # A degenerate all-uniform-distribution input would divide by zero —
    # must raise a clear error, not return NaN/inf silently.
    with pytest.raises(ValueError, match="positive"):
        compute_curvature(
            actual_token_logprobs=[-0.5],
            self_distribution_means=[-0.5],
            self_distribution_variances=[0.0],
        )


def test_curvature_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="same length"):
        compute_curvature(
            actual_token_logprobs=[-0.5, -0.5],
            self_distribution_means=[-0.5],
            self_distribution_variances=[0.3, 0.3],
        )


def test_curvature_rejects_empty_input():
    with pytest.raises(ValueError, match="must not be empty"):
        compute_curvature([], [], [])


# ── verdict — boundary behavior, and the direction is INVERTED vs Binoculars ──

def test_verdict_above_threshold_is_likely_ai():
    # Deliberately the OPPOSITE direction from binoculars_scoring.verdict()
    # — higher curvature means more likely AI here, lower score meant more
    # likely AI there. Both directions are locked in via tests specifically
    # so this asymmetry can't be silently "fixed" into matching by an
    # unwary future edit.
    assert verdict(1.5, threshold=0.9) == "likely_ai"


def test_verdict_below_threshold_is_likely_human():
    assert verdict(0.5, threshold=0.9) == "likely_human"


def test_verdict_exactly_at_threshold_is_likely_human():
    assert verdict(0.9, threshold=0.9) == "likely_human"
