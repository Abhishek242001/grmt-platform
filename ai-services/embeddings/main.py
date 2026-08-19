"""
BGE-M3 + FAISS embedding/similarity service — master build document §3.3,
deployed to the `grmt-embeddings` Lightning Studio (development_rule.md §1.2).

This is a real, runnable FastAPI service. The heavy dependencies
(sentence-transformers, faiss-cpu, torch) are NOT installed in this starter
codebase's backend venv — they're intentionally isolated here per the
master doc's guidance to keep the embedding model's footprint out of the
main API process. Install them in this service's own environment:

    cd ai-services/embeddings
    pip install -r requirements.txt

First run downloads BGE-M3 (~2.2GB) — budget real time for that, per master
doc §3.3's setup-time note. The service works with an EMPTY index (returns
no matches) until a corpus is built and loaded — see corpus-builder/.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="GRMT Embeddings Service (BGE-M3 + FAISS)")

INDEX_PATH = os.environ.get("FAISS_INDEX_PATH", "./corpus.index")
MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3")

_model = None
_index = None
_id_map: list[str] = []


def _lazy_load():
    """Load the model and index on first use, not at import time — keeps
    `uvicorn app:app --reload` fast during development when you're not
    actually testing the embedding path yet."""
    global _model, _index
    if _model is None:
        import faiss
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
        if Path(INDEX_PATH).exists():
            _index = faiss.read_index(INDEX_PATH)
        else:
            _index = faiss.IndexFlatIP(1024)  # BGE-M3 dense dim; empty until corpus-builder runs
    return _model, _index


class EmbedRequest(BaseModel):
    text: str


class QueryRequest(BaseModel):
    text: str
    top_k: int = 10


@app.get("/health")
def health():
    return {"status": "ok", "service": "grmt-embeddings", "model": MODEL_NAME, "index_size": len(_id_map)}


@app.post("/embed")
def embed(req: EmbedRequest):
    model, _ = _lazy_load()
    vec = model.encode([req.text], normalize_embeddings=True)
    return {"embedding": vec[0].tolist()}


@app.post("/query")
def query(req: QueryRequest):
    """Master doc §3.3 — normalized embeddings + IndexFlatIP == cosine similarity search."""
    import numpy as np

    model, index = _lazy_load()
    if index.ntotal == 0:
        return {"matches": [], "note": "corpus index is empty — run corpus-builder/ first"}
    vec = model.encode([req.text], normalize_embeddings=True).astype("float32")
    scores, idxs = index.search(vec, min(req.top_k, index.ntotal))
    matches = [
        {"corpus_paper_id": _id_map[i], "similarity": float(s)}
        for s, i in zip(scores[0], idxs[0])
        if i != -1 and i < len(_id_map)
    ]
    return {"matches": matches}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
