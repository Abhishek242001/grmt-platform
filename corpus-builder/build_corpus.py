"""
Reference-corpus builder — master build document §3.4. Pulls title+abstract
metadata from the Semantic Scholar Academic Graph API (bulk search endpoint)
for a target field of study, and prepares it for embedding by
ai-services/embeddings.

This is a real, runnable script — it makes live API calls, so it needs
S2AG_API_KEY set (register free at https://www.semanticscholar.org/product/api).
It intentionally does NOT call the heavier Datasets API bulk-snapshot path
described in master doc §3.4 as the "recommended for tens-of-thousands-scale"
approach — that path requires downloading and processing multi-GB snapshot
files, which is a separate, deliberately-not-automated step. This script is
the smaller, always-workable fallback: the bulk *search* endpoint, at
~1,000 papers per response, rate-limited to roughly 1 request/second with an
API key. For a real demo-scale corpus (50k-100k papers), budget the several
hours of wall-clock time master doc §3.4 describes for this fallback path,
or follow the Datasets API instructions there instead.

Usage:
    export S2AG_API_KEY=your_key_here
    python build_corpus.py --field "Computer Science" --limit 2000 --out output/corpus.jsonl
"""
import argparse
import json
import os
import time
from pathlib import Path

import httpx

S2AG_BASE = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"


def fetch_papers(field: str, limit: int, api_key: str) -> list[dict]:
    papers: list[dict] = []
    headers = {"x-api-key": api_key} if api_key else {}
    params = {
        "query": "*",
        "fields": "title,abstract,externalIds,fieldsOfStudy",
        "fieldsOfStudy": field,
    }
    token = None

    with httpx.Client(timeout=30.0) as client:
        while len(papers) < limit:
            if token:
                params["token"] = token
            resp = client.get(S2AG_BASE, params=params, headers=headers)
            if resp.status_code == 429:
                print("[RATE LIMIT] backing off 5s...")
                time.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
            batch = data.get("data", [])
            papers.extend(p for p in batch if p.get("abstract"))
            token = data.get("token")
            print(f"[FETCH] total so far: {len(papers)}")
            if not token or not batch:
                break
            time.sleep(1.1)  # stay under ~1 req/sec per master doc §3.4

    return papers[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", default="Computer Science")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--out", default="output/corpus.jsonl")
    args = parser.parse_args()

    api_key = os.environ.get("S2AG_API_KEY", "")
    if not api_key:
        print("[WARNING] S2AG_API_KEY not set — using the shared anonymous pool, which is")
        print("          capped and unreliable under load (master doc §3.4). Register a free")
        print("          key at https://www.semanticscholar.org/product/api for real use.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    papers = fetch_papers(args.field, args.limit, api_key)
    with open(out_path, "w") as f:
        for p in papers:
            f.write(json.dumps(p) + "\n")

    print(f"[OK] Wrote {len(papers)} papers to {out_path}")
    print("Next: load this file in ai-services/embeddings to embed + build the FAISS index (master doc §3.3/§3.4).")


if __name__ == "__main__":
    main()
