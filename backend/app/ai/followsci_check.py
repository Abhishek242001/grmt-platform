"""AI-generated-text detection via followsci/bert-ai-text-detector — a
BERT-base model fine-tuned specifically on 1.86M academic paragraphs from
arXiv (unlike RADAR, which was trained on general web text against a
Vicuna-7B paraphraser — a domain mismatch that's the leading suspected
cause of RADAR's bias toward flagging formal academic writing as AI, per
PROJECT_HANDOFF.md's decision record). This is the cheap thing to try
before committing to fine-tuning our own model from scratch: if this
generalizes well to OUR real academic samples, the entire training effort
becomes unnecessary.

Self-reported accuracy (99.57%) is treated with real skepticism here, not
taken at face value — it's almost certainly measured on a held-out split
from the SAME training distribution, exactly the kind of number that
hasn't generalized in any of the three approaches tried before this one.
The only number that matters is what run_calibration_set() below produces
on OUR actual samples.

MIT licensed — no commercial-use restriction, unlike RADAR.

Same disclosure as the other three check files: written where torch could
not be installed (disk space). Syntactically verified (py_compile + AST
boundary check) but not executed — needs a real run on the T4.
"""
from app.ai.grammar_check import extract_text

MODEL_ID = "followsci/bert-ai-text-detector"
MAX_TOKENS = 512  # matches the model card's own usage example

DEFAULT_THRESHOLD = 0.5

_model_cache: dict = {}


def _get_device() -> str:
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


def _load_model():
    # Lazy imports — same reasoning as radar_check.py: keeps this module
    # importable (and its orchestration logic mockable/testable) in an
    # environment without torch/transformers installed at all.
    from transformers import BertForSequenceClassification, BertTokenizer

    if "model" in _model_cache:
        return _model_cache["model"], _model_cache["tokenizer"]

    device = _get_device()
    tokenizer = BertTokenizer.from_pretrained(MODEL_ID)
    model = BertForSequenceClassification.from_pretrained(MODEL_ID).to(device)
    model.eval()

    _model_cache["model"] = model
    _model_cache["tokenizer"] = tokenizer
    return model, tokenizer


def _score_text(text: str) -> dict:
    """Label convention confirmed directly from the model card's own usage
    example (not assumed): index 0 = human, index 1 = AI-generated."""
    import torch
    import torch.nn.functional as F

    model, tokenizer = _load_model()
    device = _get_device()

    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=MAX_TOKENS)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        logits = model(**inputs).logits
        probs = F.softmax(logits, dim=-1)
        ai_probability = probs[0][1].item()

    return {"ai_probability": ai_probability}


def verdict(ai_probability: float, threshold: float = DEFAULT_THRESHOLD) -> str:
    return "likely_ai" if ai_probability > threshold else "likely_human"


def run_ai_text_detection_check(file_path: str, threshold: float = DEFAULT_THRESHOLD) -> dict:
    """Returns a dict shaped consistently with the other checks. NOT wired
    into the submission pipeline yet — needs real-sample calibration
    confirmed first, same as the other three experimental checks."""
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
            f"(followsci-BERT probability {result['ai_probability']:.4f}, threshold {threshold})."
        )

    return {
        "status": "complete",
        "ai_probability": result["ai_probability"],
        "threshold": threshold,
        "verdict": label,
        "issues": issues,
        "score": None,
    }


def run_calibration_set():
    """Same 8 samples used for all three prior attempts — directly
    comparable results. Run with:
        python3 -c "from app.ai.followsci_check import run_calibration_set as r; r()"
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
        "\nCompare directly against RADAR's result on these same 8 samples "
        "(PROJECT_HANDOFF.md has the numbers): RADAR caught all 4 AI samples "
        "but flagged 3 of 4 human samples as AI too, specifically the more "
        "FORMAL/structured ones — a domain-mismatch bias. The real question "
        "here: does academic-domain training fix that specific bias, or does "
        "it show up again?"
    )
