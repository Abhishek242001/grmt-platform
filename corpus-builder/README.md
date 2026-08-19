# Reference corpus builder

Master build document §3.4. `build_corpus.py` is the always-workable
fallback path (S2AG bulk search endpoint) — see the script's own docstring
for why the Datasets-API bulk-snapshot path (recommended for real
demo-scale corpora of 50k-100k papers) isn't automated here.

    pip install -r requirements.txt
    export S2AG_API_KEY=your_key_here
    python build_corpus.py --field "Computer Science" --limit 2000

Output lands in `output/corpus.jsonl` (gitignored — regenerable, not
something to commit). Feed it into `ai-services/embeddings` to build the
FAISS index.
