"""AI-generated-text detection via Binoculars (Hans et al., 2024), using
Qwen2.5-0.5B (observer) / Qwen2.5-0.5B-Instruct (performer) — see
PROJECT_HANDOFF.md §4.3 for the full decision record on why this pair was
chosen over the original paper's Falcon-7B pair (VRAM budget on a T4).

This module is the model-inference layer — it requires torch + transformers
+ a GPU (or at minimum a lot of patience on CPU) and CANNOT be executed or
tested in an environment without those, which is why the actual scoring
FORMULA lives separately in binoculars_scoring.py: that module has zero
torch dependency and is fully unit-tested (13 tests, hand-verified against
manually-computed expected values) without needing a GPU anywhere. This
file's job is purely to get real log-probabilities out of real models and
hand them to that already-tested math.

IMPORTANT — genuinely unverified end-to-end: this file was written without
the ability to run it. No torch/transformers/GPU is available in the
environment it was authored in (disk space ran out installing even
CPU-only torch — see the conversation this was built in). The formula
itself is independently verified (binoculars_scoring.py's tests); what's
NOT yet verified is that the transformers API is being called correctly
here — tensor shapes, that log_softmax/softmax are applied on the right
axis, that the token alignment between "predicted distribution at
position i" and "actual token at position i+1" is correct. This needs a
real run on a real GPU before being trusted. See the bottom of this file
for run_manual_verification(), a small script meant to be run directly on
the T4 Studio to sanity-check this actually works before it's wired into
the submission pipeline.
"""
import os

import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.ai.binoculars_scoring import DEFAULT_THRESHOLD, verdict
from app.ai.grammar_check import extract_text

OBSERVER_MODEL_ID = "Qwen/Qwen2.5-0.5B"
PERFORMER_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

# Binoculars scores a bounded window, not an entire long document — computing
# full-vocabulary cross-entropy at every position for a multi-thousand-word
# paper would be both slow and unnecessary (the method's own paper evaluates
# on comparably-sized windows, not full documents). First N tokens of the
# extracted body text.
MAX_TOKENS = 512

_model_cache: dict = {}


def _get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_models():
    """Lazy singleton — loading a model takes real time, this must not
    happen on every check call. Cached at module level, not per-request."""
    if "observer" in _model_cache:
        return _model_cache["observer"], _model_cache["performer"], _model_cache["tokenizer"]

    device = _get_device()
    tokenizer = AutoTokenizer.from_pretrained(OBSERVER_MODEL_ID)
    observer = AutoModelForCausalLM.from_pretrained(OBSERVER_MODEL_ID, torch_dtype="auto").to(device)
    performer = AutoModelForCausalLM.from_pretrained(PERFORMER_MODEL_ID, torch_dtype="auto").to(device)
    observer.eval()
    performer.eval()

    _model_cache["observer"] = observer
    _model_cache["performer"] = performer
    _model_cache["tokenizer"] = tokenizer
    return observer, performer, tokenizer


@torch.no_grad()
def _score_text(text: str) -> dict:
    """Runs both models over the same token sequence and computes the
    Binoculars perplexity / cross-perplexity / score, matching exactly the
    formula already unit-tested in binoculars_scoring.py (see that module's
    docstring) — computed here via torch tensor ops for efficiency rather
    than converting huge per-position vocabulary distributions to Python
    lists (the vocab is ~150k tokens; materializing that as lists per
    position would be needlessly slow and memory-heavy)."""
    observer, performer, tokenizer = _load_models()
    device = _get_device()

    encoding = tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS)
    input_ids = encoding["input_ids"].to(device)

    if input_ids.shape[1] < 2:
        raise ValueError("Text too short to score (need at least 2 tokens)")

    observer_logits = observer(input_ids).logits  # (1, seq_len, vocab_size)
    performer_logits = performer(input_ids).logits  # (1, seq_len, vocab_size)

    # Position i's logits predict the token at position i+1 — standard
    # causal-LM next-token alignment. Drop the last position (nothing to
    # predict after it) and the first actual token (nothing predicts it).
    observer_logits = observer_logits[:, :-1, :]
    performer_logits = performer_logits[:, :-1, :]
    actual_next_tokens = input_ids[:, 1:]  # (1, seq_len - 1)

    observer_log_probs = F.log_softmax(observer_logits, dim=-1)
    performer_probs = F.softmax(performer_logits, dim=-1)

    # Perplexity: observer's log-prob of the ACTUAL next token at each
    # position (gather along the vocab dim using the real token indices).
    actual_token_logprobs = observer_log_probs.gather(-1, actual_next_tokens.unsqueeze(-1)).squeeze(-1)
    perplexity = torch.exp(-actual_token_logprobs.mean()).item()

    # Cross-perplexity: at each position, cross-entropy between the
    # performer's full predicted distribution and the observer's full
    # log-distribution over the same vocabulary — this is what the
    # gather-based perplexity above deliberately does NOT do (it only
    # looks at the one actual token, not the full distribution).
    cross_entropy_per_position = -(performer_probs * observer_log_probs).sum(dim=-1)  # (1, seq_len - 1)
    cross_perplexity = torch.exp(cross_entropy_per_position.mean()).item()

    if cross_perplexity == 0:
        raise ValueError("cross_perplexity computed as zero — degenerate model output")

    return {
        "perplexity": perplexity,
        "cross_perplexity": cross_perplexity,
        "score": perplexity / cross_perplexity,
        "tokens_scored": input_ids.shape[1] - 1,
    }


def run_ai_text_detection_check(file_path: str, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Returns a dict shaped consistently with the other checks (status/
    issues/score), whether it succeeds or fails."""
    try:
        text, _page_map = extract_text(file_path)
    except Exception as e:
        return {"status": "error", "error": f"Could not extract text: {e}", "issues": [], "score": None}

    if not text.strip():
        return {"status": "error", "error": "No extractable text found in document", "issues": [], "score": None}

    try:
        result = _score_text(text)
    except Exception as e:
        return {"status": "error", "error": f"Scoring failed: {e}", "issues": [], "score": None}

    label = verdict(result["score"], threshold=threshold)
    issues = []
    if label == "likely_ai":
        issues.append(
            f"The analyzed text segment scores as likely AI-generated "
            f"(Binoculars score {result['score']:.4f}, threshold {threshold})."
        )

    return {
        "status": "complete",
        "perplexity": result["perplexity"],
        "cross_perplexity": result["cross_perplexity"],
        "binoculars_score": result["score"],
        "threshold": threshold,
        "verdict": label,
        "tokens_scored": result["tokens_scored"],
        "issues": issues,
        # Deliberately no 0-100 "score" field the way other checks have —
        # a Binoculars ratio isn't naturally a percentage, and inventing a
        # mapping to one would imply a confidence precision this method
        # doesn't actually have. binoculars_score is the real number.
        "score": None,
    }


def run_manual_verification():
    """NOT part of the automated test suite — a small script meant to be
    run directly on a GPU Studio to sanity-check this module actually
    works before it's trusted (see this file's top docstring for why that
    verification couldn't happen where this was written). Run with:
        python3 -c "from app.ai.ai_text_detection_check import run_manual_verification as r; r()"
    """
    print(f"Device: {_get_device()}")
    print(f"Loading {OBSERVER_MODEL_ID} and {PERFORMER_MODEL_ID}...")
    _load_models()
    print("Models loaded OK.\n")

    simple_repetitive_text = "The cat sat on the mat. The cat sat on the mat. The cat sat on the mat."
    varied_human_like_text = (
        "Quantum tunneling allows particles to pass through energy barriers "
        "that classical mechanics would consider insurmountable, a phenomenon "
        "with no everyday analogue whatsoever."
    )

    for label, sample in [("simple/repetitive", simple_repetitive_text), ("varied/complex", varied_human_like_text)]:
        result = _score_text(sample)
        print(f"[{label}] perplexity={result['perplexity']:.3f} cross_perplexity={result['cross_perplexity']:.3f} "
              f"score={result['score']:.4f} verdict={verdict(result['score'])}")

    print(
        "\nSanity check (not a real accuracy claim, just checking the two samples "
        "differ at all): if perplexity/score values above are identical or NaN, "
        "something is wrong with the inference code, not just the threshold."
    )


def run_calibration_set():
    """A larger (still small — 4 per class, not a real validation set)
    calibration check, built after run_realistic_verification() produced a
    worrying result: the single AI sample scored HIGHER (more "human-like")
    than the single human sample — the wrong ordering, not just the wrong
    side of a threshold. Before concluding the Qwen2.5-0.5B pair lacks
    enough discriminative power, or that one AI sample was just unlucky,
    more data points are needed. Still not remotely a real validation set
    — treat this as "does a pattern show up at all," not as an accuracy
    number to report anywhere. Run with:
        python3 -c "from app.ai.ai_text_detection_check import run_calibration_set as r; r()"
    """
    human_samples = [
        # Same real excerpt used in run_realistic_verification(), for continuity.
        "Industrial IoT deployments generate high-volume sensor streams that "
        "must be monitored for anomalies in real time. This paper presents a "
        "lightweight detection approach combining a sliding-window statistical "
        "baseline with a small gradient-boosted classifier, evaluated on three "
        "months of production line data from a mid-size manufacturing facility.",
        # A different real excerpt — from the same project's grammar-check
        # test fixture, genuinely written by a person for that purpose.
        "A Survey of Industrial AIoT. Internet of Things is important for "
        "modern manufacturing. This survey covers recent developments in "
        "industrial sensor networks and discusses open challenges that "
        "remain in the field, particularly around real-time constraints "
        "and the difficulty of deploying models at the edge.",
        # Informal human writing — a genuine style shift from the two
        # above, to check whether the detector is sensitive to register
        # rather than actual authorship.
        "Honestly I wasn't sure this would even work when I started, but "
        "after a few weeks of tinkering it's finally doing what I wanted. "
        "Still some rough edges though, and I haven't had time to test it "
        "properly against real data yet.",
        # A dense, technical human-written sentence with real domain jargon
        # (the kind of writing perplexity-based detectors sometimes flag as
        # "AI-like" precisely because it's unusually well-structured).
        "The proposed algorithm achieves O(n log n) time complexity by "
        "leveraging a balanced binary search tree for range queries, "
        "trading a modest constant-factor overhead for asymptotically "
        "superior performance on large, sparse input sets.",
    ]

    ai_samples = [
        # Same AI sample used in run_realistic_verification().
        "The proliferation of edge computing architectures has fundamentally "
        "transformed the landscape of real-time data processing in industrial "
        "environments. By leveraging distributed sensor networks in conjunction "
        "with lightweight machine learning models, organizations can achieve "
        "significant improvements in operational efficiency.",
        # A different genuinely-Claude-written sample, deliberately more
        # casual in register, to see if the earlier result was specific to
        # formal academic phrasing rather than AI-authorship itself.
        "Getting a machine learning model to actually work well in production "
        "is honestly one of the trickiest parts of the whole process. You can "
        "have great accuracy in your notebook and then watch it fall apart the "
        "moment real-world data starts flowing in, which is why monitoring and "
        "retraining pipelines matter just as much as the model itself.",
        # A short, plainly-AI-generated summary sentence — the kind of
        # compressed, hedge-free generic phrasing that's a classic
        # AI-writing tell.
        "In summary, this approach offers a robust and scalable solution "
        "to the challenges outlined above, providing significant benefits "
        "across a range of practical use cases.",
        # A genuinely-Claude-written technical explanation, matched in
        # register/topic to the dense human sample above, for a fairer
        # apples-to-apples comparison than mixing style AND authorship.
        "This algorithm attains O(n log n) time complexity through the use "
        "of a balanced binary search tree to support efficient range "
        "queries, accepting a small constant-factor cost in exchange for "
        "substantially better asymptotic performance on large, sparse "
        "datasets.",
    ]

    print(f"Device: {_get_device()}")
    _load_models()
    print("Models loaded OK.\n")

    print("=== HUMAN samples ===")
    human_scores = []
    for i, sample in enumerate(human_samples, 1):
        result = _score_text(sample)
        human_scores.append(result["score"])
        print(f"  [{i}] score={result['score']:.4f} verdict={verdict(result['score'])}")

    print("\n=== AI samples ===")
    ai_scores = []
    for i, sample in enumerate(ai_samples, 1):
        result = _score_text(sample)
        ai_scores.append(result["score"])
        print(f"  [{i}] score={result['score']:.4f} verdict={verdict(result['score'])}")

    print(f"\nHuman scores: {[round(s, 4) for s in human_scores]}")
    print(f"AI scores:    {[round(s, 4) for s in ai_scores]}")
    print(
        "\nWhat to look for: do the two groups separate AT ALL, even without "
        "the specific 0.9015 threshold — e.g. do human scores cluster higher "
        "than AI scores as groups, even if the exact cutoff needs adjusting? "
        "If the two groups are genuinely interleaved with no separation "
        "pattern, that's a real signal this specific model pair may not have "
        "enough discriminative power for this task, not just a threshold "
        "calibration problem."
    )


def run_length_diagnostic():
    """Built after run_calibration_set() showed a genuinely backward,
    fully-interleaved result (no threshold could fix it) — this isolates
    ONE variable (text length) before concluding the model pair itself
    lacks discriminative power. Binoculars' own paper validates on longer
    passages than the ~40-70 word snippets used in run_calibration_set();
    perplexity/cross-perplexity estimates over few tokens are inherently
    noisier. If longer passages separate cleanly and short ones don't,
    that's a real, useful, different finding than "the model pair doesn't
    work" — it would mean the check needs a minimum-length gate, not a
    bigger model. If longer passages STILL don't separate, that rules
    length out and points more clearly at model capacity. Run with:
        python3 -c "from app.ai.ai_text_detection_check import run_length_diagnostic as r; r()"
    """
    # ~230 words — a genuine excerpt from the same real test paper used
    # elsewhere (IEEE-filled-realistic.docx), several sentences longer
    # than the calibration-set human samples.
    human_long = (
        "Industrial IoT deployments generate high-volume sensor streams that "
        "must be monitored for anomalies in real time. This paper presents a "
        "lightweight detection approach combining a sliding-window statistical "
        "baseline with a small gradient-boosted classifier, evaluated on three "
        "months of production line data from a mid-size manufacturing facility. "
        "Existing anomaly detection approaches often assume cloud connectivity, "
        "which is not always available on factory floors. The proposed pipeline "
        "maintains a rolling statistical baseline over a configurable window, "
        "updated every 500ms. Detection accuracy remains stable even under "
        "moderate sensor noise, and the false-positive rate stays below two "
        "percent across all three deployment sites tested. We compare our "
        "approach against two baseline methods: a fixed-threshold detector and "
        "a standard isolation forest trained offline on historical data. The "
        "fixed-threshold detector suffers from a high false-positive rate "
        "whenever ambient noise increases seasonally, while the isolation "
        "forest requires periodic retraining that isn't always feasible given "
        "limited compute on edge devices. Our method avoids both drawbacks "
        "by continuously adapting its baseline without requiring a full "
        "retraining cycle, making it substantially more practical for "
        "resource-constrained industrial deployments."
    )

    # ~230 words — genuinely written by Claude for this specific test, on
    # a comparable topic and length, not adapted or shortened from anywhere.
    ai_long = (
        "The proliferation of edge computing architectures has fundamentally "
        "transformed the landscape of real-time data processing in industrial "
        "environments. By leveraging distributed sensor networks in conjunction "
        "with lightweight machine learning models, organizations can achieve "
        "significant improvements in operational efficiency while simultaneously "
        "reducing the latency associated with traditional cloud-based analytics "
        "pipelines. This paradigm shift represents a critical advancement in the "
        "field of industrial automation and predictive maintenance strategies. "
        "Furthermore, the integration of statistical baseline methods with "
        "machine learning classifiers offers a compelling balance between "
        "computational efficiency and detection accuracy. Traditional approaches "
        "that rely solely on fixed thresholds often struggle to adapt to the "
        "natural variability present in real-world sensor data, leading to "
        "elevated false-positive rates that undermine operator confidence in "
        "the system. By contrast, adaptive statistical methods can continuously "
        "adjust to changing baseline conditions, providing a more robust "
        "foundation for anomaly detection across diverse operating environments. "
        "It is also worth noting that the practical deployment of such systems "
        "must carefully balance model complexity against the constrained "
        "computational resources typically available on edge hardware, "
        "ensuring that detection latency remains low enough to support "
        "genuinely real-time monitoring and intervention."
    )

    print(f"Device: {_get_device()}")
    _load_models()
    print("Models loaded OK.\n")

    for label, sample in [("HUMAN (long, real excerpt)", human_long), ("AI (long, genuinely Claude-generated)", ai_long)]:
        result = _score_text(sample)
        print(f"[{label}]")
        print(f"  tokens_scored={result['tokens_scored']} perplexity={result['perplexity']:.3f} "
              f"cross_perplexity={result['cross_perplexity']:.3f} score={result['score']:.4f} "
              f"verdict={verdict(result['score'])}")

    print(
        "\nIf these separate correctly (human=likely_human, AI=likely_ai) where "
        "the short samples didn't, that points to a minimum-length requirement "
        "for this check, not a fundamentally unusable model pair. If they STILL "
        "don't separate, length isn't the explanation."
    )


def run_realistic_verification():
    """A stronger check than run_manual_verification(): one sample is
    genuine human-authored academic prose (an excerpt actually written by
    a person for a real IEEE-format test paper used elsewhere in this
    project), the other is genuinely LLM-generated text on a comparable
    topic (written by Claude, the AI building this feature, specifically
    for this test — an actual AI sample, not a stand-in). This is a real,
    if small (n=1 each), accuracy signal — unlike run_manual_verification()
    above, which only checks the code runs sanely, not whether detection
    itself works. Run with:
        python3 -c "from app.ai.ai_text_detection_check import run_realistic_verification as r; r()"
    """
    # Genuine human-authored text — an excerpt from the abstract of a real
    # test paper used elsewhere in this project (IEEE-filled-realistic.docx,
    # written by hand for the table/figure check's real-document validation).
    human_written = (
        "Industrial IoT deployments generate high-volume sensor streams that "
        "must be monitored for anomalies in real time. This paper presents a "
        "lightweight detection approach combining a sliding-window statistical "
        "baseline with a small gradient-boosted classifier, evaluated on three "
        "months of production line data from a mid-size manufacturing facility. "
        "Existing anomaly detection approaches often assume cloud connectivity, "
        "which is not always available on factory floors."
    )

    # Genuinely AI-generated — written by Claude for this specific test, on
    # a comparable academic/technical topic, not adapted from anywhere.
    ai_written = (
        "The proliferation of edge computing architectures has fundamentally "
        "transformed the landscape of real-time data processing in industrial "
        "environments. By leveraging distributed sensor networks in conjunction "
        "with lightweight machine learning models, organizations can achieve "
        "significant improvements in operational efficiency while simultaneously "
        "reducing the latency associated with traditional cloud-based analytics "
        "pipelines. This paradigm shift represents a critical advancement in the "
        "field of industrial automation and predictive maintenance strategies."
    )

    print(f"Device: {_get_device()}")
    _load_models()
    print("Models loaded OK.\n")

    for label, sample in [("HUMAN-written (real excerpt)", human_written), ("AI-written (genuinely Claude-generated)", ai_written)]:
        result = _score_text(sample)
        print(f"[{label}]")
        print(f"  perplexity={result['perplexity']:.3f} cross_perplexity={result['cross_perplexity']:.3f} "
              f"score={result['score']:.4f} verdict={verdict(result['score'])}")

    print(
        "\nThis is what actually matters: does the human sample score 'likely_human' "
        "and the AI sample score 'likely_ai'? If yes, the threshold is at least "
        "roughly plausible for real content, not just the toy examples above. If "
        "no, or if they're close together, the threshold needs real recalibration "
        "before this check goes anywhere near real submissions — this is n=1 "
        "per class, not a real validation set, so don't over-trust a single "
        "correct (or incorrect) result either way."
    )

