"""Fast-DetectGPT model inference layer — the counterpart to
fast_detect_gpt_scoring.py's pure math, requiring torch + transformers + a
GPU, same split-and-caveat structure as ai_text_detection_check.py (see
that file's docstring for why: this was written where torch could not be
installed at all — disk space ran out even for a CPU-only build — so this
file is UNVERIFIED beyond passing a syntax/AST check. It needs a real run
on the T4 Studio before being trusted, same as the Binoculars module was.

Uses a SINGLE model (Qwen2.5-3B, base, not instruct — Fast-DetectGPT scores
raw text under one language model, no observer/performer pair) rather than
Binoculars' two models. This is a genuinely different bet, not a resize of
what already failed: freeing the VRAM Binoculars split across two 0.5B
models lets this use one meaningfully larger 3B model instead (~7-8GB in
FP16, still comfortable headroom on a T4).
"""
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.ai.fast_detect_gpt_scoring import compute_curvature, verdict
from app.ai.grammar_check import extract_text

MODEL_ID = "Qwen/Qwen2.5-3B"

# Same reasoning as ai_text_detection_check.py's MAX_TOKENS — a bounded
# scoring window, not full-document inference.
MAX_TOKENS = 512

_model_cache: dict = {}


def _get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    if "model" in _model_cache:
        return _model_cache["model"], _model_cache["tokenizer"]

    device = _get_device()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto").to(device)
    model.eval()

    _model_cache["model"] = model
    _model_cache["tokenizer"] = tokenizer
    return model, tokenizer


@torch.no_grad()
def _score_text(text: str) -> dict:
    """Runs the model once over the text, extracts the actual per-position
    log-probs plus each position's self-distribution mean/variance, and
    hands them to the already-tested compute_curvature()."""
    model, tokenizer = _load_model()
    device = _get_device()

    encoding = tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS)
    input_ids = encoding["input_ids"].to(device)

    if input_ids.shape[1] < 2:
        raise ValueError("Text too short to score (need at least 2 tokens)")

    logits = model(input_ids).logits  # (1, seq_len, vocab_size)
    logits = logits[:, :-1, :]  # position i predicts token i+1, same alignment as ai_text_detection_check.py
    actual_next_tokens = input_ids[:, 1:]

    log_probs = F.log_softmax(logits, dim=-1)
    probs = F.softmax(logits, dim=-1)

    # Per-position actual log-prob of the real next token.
    actual_logprobs = log_probs.gather(-1, actual_next_tokens.unsqueeze(-1)).squeeze(-1)  # (1, seq_len-1)

    # Per-position self-distribution mean (E[log P]) and variance
    # (E[(log P)^2] - mean^2) — computed directly via tensor ops rather
    # than converting to Python lists per position (same efficiency
    # reasoning as ai_text_detection_check.py's cross-entropy computation;
    # the formula is identical to distribution_mean_and_variance() in
    # fast_detect_gpt_scoring.py, just vectorized).
    position_means = (probs * log_probs).sum(dim=-1)  # (1, seq_len-1)
    position_second_moments = (probs * log_probs.pow(2)).sum(dim=-1)
    position_variances = position_second_moments - position_means.pow(2)

    result = compute_curvature(
        actual_token_logprobs=actual_logprobs.squeeze(0).tolist(),
        self_distribution_means=position_means.squeeze(0).tolist(),
        self_distribution_variances=position_variances.squeeze(0).tolist(),
    )
    result["tokens_scored"] = input_ids.shape[1] - 1
    return result


def run_calibration_set(threshold_to_test: float = 0.0):
    """Mirrors ai_text_detection_check.run_calibration_set()'s samples
    exactly (same 4 human + 4 AI texts) so the two methods' results are
    directly comparable on identical input, not different text choices
    muddying the comparison. threshold_to_test is deliberately required
    with an obvious placeholder default (0.0) — there is no calibrated
    threshold for this model yet; the whole point of running this is to
    see where a reasonable threshold might even be, not to apply one that
    doesn't exist. Run with:
        python3 -c "from app.ai.fast_detect_gpt_check import run_calibration_set as r; r()"
    """
    human_samples = [
        "Industrial IoT deployments generate high-volume sensor streams that "
        "must be monitored for anomalies in real time. This paper presents a "
        "lightweight detection approach combining a sliding-window statistical "
        "baseline with a small gradient-boosted classifier, evaluated on three "
        "months of production line data from a mid-size manufacturing facility.",
        "A Survey of Industrial AIoT. Internet of Things is important for "
        "modern manufacturing. This survey covers recent developments in "
        "industrial sensor networks and discusses open challenges that "
        "remain in the field, particularly around real-time constraints "
        "and the difficulty of deploying models at the edge.",
        "Honestly I wasn't sure this would even work when I started, but "
        "after a few weeks of tinkering it's finally doing what I wanted. "
        "Still some rough edges though, and I haven't had time to test it "
        "properly against real data yet.",
        "The proposed algorithm achieves O(n log n) time complexity by "
        "leveraging a balanced binary search tree for range queries, "
        "trading a modest constant-factor overhead for asymptotically "
        "superior performance on large, sparse input sets.",
    ]

    ai_samples = [
        "The proliferation of edge computing architectures has fundamentally "
        "transformed the landscape of real-time data processing in industrial "
        "environments. By leveraging distributed sensor networks in conjunction "
        "with lightweight machine learning models, organizations can achieve "
        "significant improvements in operational efficiency.",
        "Getting a machine learning model to actually work well in production "
        "is honestly one of the trickiest parts of the whole process. You can "
        "have great accuracy in your notebook and then watch it fall apart the "
        "moment real-world data starts flowing in, which is why monitoring and "
        "retraining pipelines matter just as much as the model itself.",
        "In summary, this approach offers a robust and scalable solution "
        "to the challenges outlined above, providing significant benefits "
        "across a range of practical use cases.",
        "This algorithm attains O(n log n) time complexity through the use "
        "of a balanced binary search tree to support efficient range "
        "queries, accepting a small constant-factor cost in exchange for "
        "substantially better asymptotic performance on large, sparse "
        "datasets.",
    ]

    print(f"Device: {_get_device()}")
    print(f"Loading {MODEL_ID}...")
    _load_model()
    print("Model loaded OK.\n")

    print("=== HUMAN samples ===")
    human_curvatures = []
    for i, sample in enumerate(human_samples, 1):
        result = _score_text(sample)
        human_curvatures.append(result["curvature"])
        print(f"  [{i}] curvature={result['curvature']:.4f}")

    print("\n=== AI samples ===")
    ai_curvatures = []
    for i, sample in enumerate(ai_samples, 1):
        result = _score_text(sample)
        ai_curvatures.append(result["curvature"])
        print(f"  [{i}] curvature={result['curvature']:.4f}")

    print(f"\nHuman curvatures: {[round(c, 4) for c in human_curvatures]}")
    print(f"AI curvatures:    {[round(c, 4) for c in ai_curvatures]}")
    print(
        "\nRecall: HIGHER curvature = more likely AI here (opposite direction "
        "from the Binoculars score). Look for: do AI curvatures cluster "
        "meaningfully HIGHER than human curvatures as groups? If yes, there's "
        "a real signal and a threshold can be picked between the two clusters. "
        "If they're interleaved the way Binoculars' results were, that's "
        "evidence against a single ~3B model being enough either, not just "
        "this specific one."
    )
