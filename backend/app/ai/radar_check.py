"""AI-generated-text detection via RADAR (Hu et al., NeurIPS 2023,
"RADAR: Robust AI-Text Detection via Adversarial Learning") — a genuinely
different approach from the two already-tried and already-rejected zero-shot
methods (see binoculars_scoring.py / fast_detect_gpt_scoring.py and
PROJECT_HANDOFF.md's decision record for why both failed: proxy-model/
generator mismatch and domain unfamiliarity collapsed the statistical
signal those methods depend on).

RADAR is a TRAINED classifier, not a zero-shot statistical proxy — it
directly learned "human vs AI" as a supervised task via adversarial
training against a paraphraser, rather than inferring it indirectly
through perplexity math. This sidesteps the exact failure mode that sank
Binoculars and Fast-DetectGPT here: it doesn't need to itself be a capable
enough language model to notice a subtle statistical mismatch, it just
needs to be a good discriminator, which needed far less capacity to train
well (RoBERTa-large, ~355M params — smaller than even the Qwen2.5-0.5B
pair that already failed).

IMPORTANT — same disclosure as the other two check files: written where
torch/transformers could not be installed (disk space). Syntactically
verified (py_compile + AST function-boundary check — see the earlier bug
this caught in ai_text_detection_check.py) but NOT executed. Needs a real
run on the T4 before being trusted.

LICENSING NOTE: RADAR-Vicuna-7B is released under a non-commercial license
(inherited from Vicuna-7B-v1.1, which was itself trained on data with its
own restrictions). Worth confirming this is compatible with how this
platform is ultimately deployed before shipping it to real users — this is
a genuine constraint the two zero-shot methods didn't have (those used
Apache/permissively-licensed base models).
"""
from app.ai.grammar_check import extract_text

MODEL_ID = "TrustSafeAI/RADAR-Vicuna-7B"
MAX_TOKENS = 512  # matches the official usage example in IBM's own RADAR repo

# A trained classifier outputs a genuine probability, not an arbitrary
# ratio/curvature statistic needing calibration from scratch the way the
# other two methods did — 0.5 is a reasonable, standard starting point for
# a binary classifier's decision boundary. Still worth validating against
# real samples before trusting it blindly; see run_calibration_set() below.
DEFAULT_THRESHOLD = 0.5

_model_cache: dict = {}


def _get_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    # Imports deliberately deferred to inside functions, not module level —
    # lets this module be imported (and its non-model orchestration logic
    # tested/mocked) in an environment without torch/transformers installed
    # at all, which every other function in this file below except the
    # actual model call benefits from.
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    if "model" in _model_cache:
        return _model_cache["model"], _model_cache["tokenizer"]

    device = _get_device()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID).to(device)
    model.eval()

    _model_cache["model"] = model
    _model_cache["tokenizer"] = tokenizer
    return model, tokenizer


def _score_text(text: str) -> dict:
    """Returns the model's own probability that the text is AI-generated —
    unlike the other two checks, there's no custom formula here to
    separately unit-test; the "verification" that matters is confirming
    the label convention is read correctly (index 0 = AI-generated
    probability, per IBM's own official usage example) and that real
    evaluation produces sane, separating results."""
    import torch
    import torch.nn.functional as F

    model, tokenizer = _load_model()
    device = _get_device()

    inputs = tokenizer([text], padding=True, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits
        ai_probability = F.log_softmax(logits, dim=-1)[:, 0].exp().item()

    return {"ai_probability": ai_probability}


def verdict(ai_probability: float, threshold: float = DEFAULT_THRESHOLD) -> str:
    return "likely_ai" if ai_probability > threshold else "likely_human"


def run_ai_text_detection_check(file_path: str, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Returns a dict shaped consistently with the other checks (status/
    issues/score), whether it succeeds or fails. NOT wired into the
    submission pipeline yet — same reasoning as the other two experimental
    checks: needs real-sample calibration confirmed first."""
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

    label = verdict(result["ai_probability"], threshold=threshold)
    issues = []
    if label == "likely_ai":
        issues.append(
            f"The analyzed text segment scores as likely AI-generated "
            f"(RADAR probability {result['ai_probability']:.4f}, threshold {threshold})."
        )

    return {
        "status": "complete",
        "ai_probability": result["ai_probability"],
        "threshold": threshold,
        "verdict": label,
        "issues": issues,
        "score": None,  # same reasoning as the other two checks — a probability isn't a 0-100 quality score
    }


def run_calibration_set():
    """Same 8 samples (4 human, 4 AI) used for both prior methods' failed
    calibration attempts — directly comparable results, not muddied by
    different text choices. Run with:
        python3 -c "from app.ai.radar_check import run_calibration_set as r; r()"
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
    human_probs = []
    for i, sample in enumerate(human_samples, 1):
        result = _score_text(sample)
        human_probs.append(result["ai_probability"])
        print(f"  [{i}] ai_probability={result['ai_probability']:.4f} verdict={verdict(result['ai_probability'])}")

    print("\n=== AI samples ===")
    ai_probs = []
    for i, sample in enumerate(ai_samples, 1):
        result = _score_text(sample)
        ai_probs.append(result["ai_probability"])
        print(f"  [{i}] ai_probability={result['ai_probability']:.4f} verdict={verdict(result['ai_probability'])}")

    correct = sum(1 for p in human_probs if p <= DEFAULT_THRESHOLD) + sum(1 for p in ai_probs if p > DEFAULT_THRESHOLD)
    print(f"\nHuman probabilities: {[round(p, 4) for p in human_probs]}")
    print(f"AI probabilities:    {[round(p, 4) for p in ai_probs]}")
    print(f"\nCorrect at default threshold ({DEFAULT_THRESHOLD}): {correct}/8")
    print(
        "\nUnlike the other two methods, this outputs a genuine trained "
        "probability — look for AI probabilities clustering close to 1.0 "
        "and human probabilities clustering close to 0.0, not just "
        "'higher than' each other. A classifier that's actually working "
        "should look confident, not just directionally correct."
    )
