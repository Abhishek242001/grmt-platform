"""Binoculars scoring math (Hans et al., 2024, "Spotting LLMs With Binoculars") —
deliberately separated from model inference (ai_text_detection_check.py) so this
module has zero dependency on torch/transformers/GPU and can be unit-tested with
plain numpy anywhere, including environments with no GPU at all.

The method: given text scored by two related language models — an "observer"
(M1) and a "performer" (M2) — compute the ratio of the text's perplexity under
M1 to its cross-perplexity between M1 and M2. AI-generated text tends to be
"unsurprising" to both models in a correlated way (low ratio); human text
surprises the performer more than the observer (higher ratio).

    perplexity(s | M1)       = exp( -1/n * sum_i log P_M1(s_i | s_<i) )
    cross_perplexity(M1, M2 | s) = exp( -1/n * sum_i sum_v P_M2(v|s_<i) * log P_M1(v|s_<i) )
    score = perplexity / cross_perplexity

Lower score => more likely AI-generated. The threshold that separates
"likely AI" from "likely human" is SPECIFIC TO THE MODEL PAIR — the commonly
cited ~0.9015 threshold was calibrated for the original paper's Falcon-7B /
Falcon-7B-instruct pair (see PROJECT_HANDOFF.md §4.3 for why this project
uses a different, much smaller pair instead). That threshold is NOT reused
here without recalibration — see DEFAULT_THRESHOLD's docstring below.
"""
import math

# Placeholder pending real calibration against the actual Qwen2.5-0.5B /
# Qwen2.5-0.5B-Instruct pair on real human and real AI-generated text — see
# PROJECT_HANDOFF.md §4.3. Using the Falcon-pair paper's ~0.9015 here would
# be scientifically unjustified: the score distribution depends on the
# specific model pair, not just the method. DO NOT ship this threshold to
# production without first running it against known-human and known-AI
# sample text on the real model pair and adjusting based on what's observed.
DEFAULT_THRESHOLD = 0.9015


def compute_perplexity(observer_token_logprobs: list[float]) -> float:
    """Perplexity of the text under the observer model alone.

    observer_token_logprobs: log P_M1(actual_token_i | tokens_<i) for each
    token position i in the text (excluding the first token, which has no
    preceding context to condition on)."""
    if not observer_token_logprobs:
        raise ValueError("observer_token_logprobs must not be empty")
    mean_neg_log_prob = -sum(observer_token_logprobs) / len(observer_token_logprobs)
    return math.exp(mean_neg_log_prob)


def compute_cross_perplexity(
    performer_next_token_probs: list[list[float]],
    observer_next_token_logprobs: list[list[float]],
) -> float:
    """Cross-perplexity between observer (M1) and performer (M2).

    At each token position, this scores M1's assessment of M2's FULL
    predicted next-token distribution (not just the single observed
    token) — this is what distinguishes cross-perplexity from ordinary
    perplexity, and is the core of the Binoculars method.

    performer_next_token_probs[i]: M2's softmax distribution (probabilities,
        summing to ~1.0) over the vocabulary at position i.
    observer_next_token_logprobs[i]: M1's log-softmax distribution over the
        SAME vocabulary at the SAME position i.

    Both lists must be the same length (one entry per token position) and
    each inner list the same length as the other's corresponding entry
    (both cover the same vocabulary)."""
    if not performer_next_token_probs:
        raise ValueError("performer_next_token_probs must not be empty")
    if len(performer_next_token_probs) != len(observer_next_token_logprobs):
        raise ValueError("performer and observer distributions must cover the same number of positions")

    position_cross_entropies = []
    for perf_dist, obs_logdist in zip(performer_next_token_probs, observer_next_token_logprobs):
        if len(perf_dist) != len(obs_logdist):
            raise ValueError("performer and observer distributions must cover the same vocabulary size")
        cross_entropy = -sum(p * logp for p, logp in zip(perf_dist, obs_logdist))
        position_cross_entropies.append(cross_entropy)

    mean_cross_entropy = sum(position_cross_entropies) / len(position_cross_entropies)
    return math.exp(mean_cross_entropy)


def binoculars_score(
    observer_token_logprobs: list[float],
    performer_next_token_probs: list[list[float]],
    observer_next_token_logprobs: list[list[float]],
) -> dict:
    """Full Binoculars score for one piece of text. Returns perplexity,
    cross-perplexity, and their ratio — never just the ratio alone, so a
    caller can sanity-check the intermediate values (e.g. a NaN/inf
    cross-perplexity from a degenerate distribution is much easier to spot
    with the raw numbers in front of you than from the ratio alone)."""
    perplexity = compute_perplexity(observer_token_logprobs)
    cross_perplexity = compute_cross_perplexity(performer_next_token_probs, observer_next_token_logprobs)
    if cross_perplexity == 0:
        raise ValueError("cross_perplexity computed as zero — degenerate input distributions")
    return {
        "perplexity": perplexity,
        "cross_perplexity": cross_perplexity,
        "score": perplexity / cross_perplexity,
    }


def verdict(score: float, threshold: float = DEFAULT_THRESHOLD) -> str:
    """"likely_ai" if score is below threshold (text is suspiciously
    predictable to both models in a correlated way), else "likely_human"."""
    return "likely_ai" if score < threshold else "likely_human"
