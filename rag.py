import sys
import json
from pathlib import Path
import numpy as np
from llm import embed

VECS = Path("data/index/vectors.npy")
CHUNKS = Path("data/index/chunks.json")
MIN_SCORE = 0.62

if not VECS.exists():
    raise FileNotFoundError("data/index/vectors.npy missing: run  python build_index.py  first")

_vecs = np.load(VECS)
_chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))


def search(q, k=5, min_score=MIN_SCORE):
    v = embed([q], task="RETRIEVAL_QUERY")[0]
    scores = _vecs @ v
    out = []
    for i in np.argsort(-scores)[:k]:
        s = float(scores[i])
        if s < min_score:
            continue
        c = dict(_chunks[i])
        c["score"] = round(s, 3)
        out.append(c)
    return out


def by_id(cid):
    return next((c for c in _chunks if c["id"] == cid), None)


if __name__ == "__main__":
    qs = sys.argv[1:] or [
        "seller not refunding money after I returned a defective product",
        "how many years do I have to file a consumer complaint",
        "which commission handles a complaint of 50000 rupees",
        "duties of online marketplace towards customer grievances",
        "my landlord is not returning my security deposit",
    ]
    for q in qs:
        print(f"\nQ: {q}")
        for h in search(q, min_score=0):
            mark = "" if h["score"] >= MIN_SCORE else "  (below cutoff)"
            print(f"  {h['score']:.3f}  {h['id']:12} {h['title'][:50]}{mark}")
