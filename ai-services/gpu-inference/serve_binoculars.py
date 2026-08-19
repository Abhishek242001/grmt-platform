"""
Binoculars + Fast-DetectGPT AI-text-detection service — master build
document §3.6, deployed to the `grmt-gpu-inference` Lightning Studio
(development_rule.md §1.2/§1.3).

Requires a real GPU (~15-16GB VRAM for Binoculars' dual falcon-7b pair in
FP16) — see master doc §3.6 and development_rule.md §1 for the L4 sizing
rationale and the "run sequentially, not co-resident with the LLM service"
guidance. Heavy deps (torch, transformers, binoculars) are isolated to this
service's own environment, same pattern as ai-services/embeddings.

This is a SOFT GATE ONLY signal per master doc §1.1/§1.4 — the backend's
Gate Rule Engine (backend/app/core/gate_engine.py) already refuses to treat
ai_content_pct as a hard gate even if this service's score is extreme;
that constraint does not depend on this service behaving correctly, but
this service must still never claim more confidence than it has. A flag is
only meaningful when BOTH Binoculars and Fast-DetectGPT agree — see
combine_signals() below, straight from master doc §3.6.
"""
import os

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="GRMT GPU Inference Service (Binoculars + Fast-DetectGPT)")

# Calibrate against real academic text before trusting these in production —
# master doc §3.6 explicitly warns detector thresholds are domain-sensitive.
BINOCULARS_THRESHOLD = float(os.environ.get("BINOCULARS_THRESHOLD", "0.9"))
FASTDETECT_THRESHOLD = float(os.environ.get("FASTDETECT_THRESHOLD", "0.5"))

_binoculars_model = None


def _lazy_load_binoculars():
    global _binoculars_model
    if _binoculars_model is None:
        from binoculars import Binoculars  # heavy import — only on first real use

        _binoculars_model = Binoculars()
    return _binoculars_model


class DetectRequest(BaseModel):
    text: str


def combine_signals(binoculars_score: float, fastdetect_score: float) -> dict:
    """master doc §3.6 — only surface a flag when BOTH detectors agree."""
    bino_flag = binoculars_score < BINOCULARS_THRESHOLD  # lower Binoculars score = more likely AI
    fast_flag = fastdetect_score > FASTDETECT_THRESHOLD  # higher Fast-DetectGPT score = more likely AI
    return {
        "binoculars_score": binoculars_score,
        "binoculars_flag": bino_flag,
        "fastdetect_score": fastdetect_score,
        "fastdetect_flag": fast_flag,
        "combined_flag": bino_flag and fast_flag,
        "confidence": "high" if (bino_flag and fast_flag) else "low",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "grmt-gpu-inference", "model_loaded": _binoculars_model is not None}


@app.post("/detect")
def detect(req: DetectRequest):
    """
    Runs both detectors and returns the combined, conservative signal. In
    this starter codebase Fast-DetectGPT is stubbed (see the TODO below) —
    Binoculars is wired for real. Wire Fast-DetectGPT the same way once its
    scoring model is chosen and calibrated (master doc §3.6).
    """
    model = _lazy_load_binoculars()
    binoculars_score = model.predict(req.text)

    # TODO: replace with a real Fast-DetectGPT call once that scoring model
    # is deployed alongside Binoculars on this Studio — see master doc §3.6.
    # Returning a neutral placeholder here means combined_flag can currently
    # only ever be True if Binoculars alone is extremely confident AND this
    # placeholder happens to cross FASTDETECT_THRESHOLD, which is why this
    # stub deliberately returns a LOW score (0.0) — biasing toward "don't
    # flag" rather than fabricating false confidence from an unimplemented
    # detector. Do not treat this endpoint's combined_flag as production-
    # ready until the real Fast-DetectGPT call replaces this stub.
    fastdetect_score = 0.0

    return combine_signals(binoculars_score, fastdetect_score)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
