"""Fast-DetectGPT scoring math (Bao et al., 2023, "Fast-DetectGPT: Efficient
Zero-Shot Detection of Machine-Generated Text via Conditional Probability
Curvature") — deliberately separated from model inference
(fast_detect_gpt_check.py) for the same reason binoculars_scoring.py is
separate from ai_text_detection_check.py: zero torch dependency, fully
unit-testable with plain Python anywhere, no GPU needed.

Built as a second experiment after the Binoculars method (see
binoculars_scoring.py / ai_text_detection_check.py) showed a genuinely
backward, non-separating result with a small (0.5B+0.5B) model pair —
confirmed via real testing on a T4, not assumed. Fast-DetectGPT only needs
ONE model rather than two, so the same VRAM budget can go toward a single
meaningfully larger model (Qwen2.5-3B, ~7-8GB in FP16) instead of splitting
it across two small ones — a genuinely different bet, not just a resize of
what already failed.

The method: DetectGPT's original idea is that AI-generated text sits at a
local maximum of the model's own probability landscape — small perturbations
to the text tend to *decrease* its probability under the model, more so for
AI-generated text than human text. Fast-DetectGPT approximates this without
literally generating and rescoring thousands of perturbations (DetectGPT's
expensive approach) by instead analytically computing, at each token
position, the MEAN and VARIANCE of "log-probability of a token sampled from
the model's own predicted distribution at this position" — then measuring
how many standard deviations the ACTUAL text's log-probability sits above
that expectation (a z-score, called the "curvature" statistic).

    mean_i = sum_v p_i(v) * log p_i(v)              (expected self-log-prob; = -entropy)
    var_i  = sum_v p_i(v) * (log p_i(v))^2 - mean_i^2
    actual_i = log p_i(x_i)                          (log-prob of the ACTUAL next token)

    curvature = (sum_i actual_i - sum_i mean_i) / sqrt(sum_i var_i)

Higher curvature => the actual text is more probable than "typical" samples
from the model's own distribution => more likely AI-generated. As with
Binoculars, the threshold separating "likely AI" from "likely human" is
SPECIFIC TO THE SCORING MODEL — not reused from any other paper's
calibration without first validating on real samples with the actual model
in use (Qwen2.5-3B here). See ai_text_detection_check.py's calibration
functions for the Binoculars precedent this follows.
"""
import math

# No default threshold shipped — deliberately. Binoculars' ported threshold
# (from a completely different model pair) turned out to be actively
# misleading rather than just imprecise (see PROJECT_HANDOFF.md's decision
# record). Rather than repeat that mistake with an invented placeholder
# number for a method/model combination that has never been calibrated at
# all, callers must pass an explicit threshold, forcing a conscious choice
# rather than a silently-wrong default.


def compute_curvature(
    actual_token_logprobs: list[float],
    self_distribution_means: list[float],
    self_distribution_variances: list[float],
) -> dict:
    """Returns the raw components and the final curvature statistic —
    never just the statistic alone, so a caller can sanity-check the
    intermediate sums (e.g. a near-zero total variance, which would make
    the ratio wildly unstable, is much easier to spot with the raw number
    in front of you).

    actual_token_logprobs[i]: log P(actual token at position i | context)
    self_distribution_means[i]: E_{v~P}[log P(v | context)] at position i
    self_distribution_variances[i]: Var_{v~P}[log P(v | context)] at position i

    All three lists must be the same length (one entry per scored token
    position)."""
    if not actual_token_logprobs:
        raise ValueError("actual_token_logprobs must not be empty")
    n = len(actual_token_logprobs)
    if len(self_distribution_means) != n or len(self_distribution_variances) != n:
        raise ValueError("all three input lists must be the same length")

    total_actual = sum(actual_token_logprobs)
    total_mean = sum(self_distribution_means)
    total_variance = sum(self_distribution_variances)

    if total_variance <= 0:
        raise ValueError(
            f"total_variance must be positive to compute a stable curvature score, got {total_variance}"
        )

    curvature = (total_actual - total_mean) / math.sqrt(total_variance)
    return {
        "total_actual_logprob": total_actual,
        "total_expected_logprob": total_mean,
        "total_variance": total_variance,
        "curvature": curvature,
    }


def distribution_mean_and_variance(probs: list[float], logprobs: list[float]) -> tuple[float, float]:
    """Computes E[log P] and Var[log P] for one token position's full
    predicted distribution — the per-position building blocks that feed
    compute_curvature() above. Split out as its own tested function since
    it's the part most likely to have a subtle sign/indexing bug (e.g.
    E[X^2] vs (E[X])^2 confusion) if inlined directly into a larger loop."""
    if len(probs) != len(logprobs):
        raise ValueError("probs and logprobs must be the same length (same vocabulary)")
    if not probs:
        raise ValueError("probs must not be empty")

    mean = sum(p * lp for p, lp in zip(probs, logprobs))
    second_moment = sum(p * (lp ** 2) for p, lp in zip(probs, logprobs))
    variance = second_moment - mean ** 2
    return mean, variance


def verdict(curvature: float, threshold: float) -> str:
    """"likely_ai" if curvature is ABOVE threshold (text is more probable
    than "typical" self-samples — the opposite direction from Binoculars'
    score, where LOWER meant more likely AI). Threshold has no default —
    see this module's docstring for why."""
    return "likely_ai" if curvature > threshold else "likely_human"
