"""Measure retrieval on the labeled question set: recall@k, MRR and per-query latency.

Run: uv run python -m app.search.evaluate [--k 5] [--mode hybrid|full_text|embedding] [--set dev|holdout]

"dev" is questions.yaml, which search was tuned on. "holdout" is holdout.yaml, written by a second model that
never saw the search code (app/search/write_questions.py); it is only measured, never tuned on.
"""

import argparse
import json
import re
import statistics
import time
from pathlib import Path

import yaml

from app.search import search as s

EVAL = Path(__file__).resolve().parents[3] / "eval" / "retrieval"
SETS = {"dev": EVAL / "questions.yaml", "holdout": EVAL / "holdout.yaml"}


def _covers(expected: str, section_id: str) -> bool:
    return re.search(r"(^|\()" + re.escape(expected) + r"($|[ .(),])", section_id) is not None


def evaluate(k: int = 5, mode: str = "hybrid", qset: str = "dev") -> dict:
    qs = yaml.safe_load(SETS[qset].read_text())["questions"]
    s.search("warm up the embedding model")  # first call loads the model; not counted
    hits_at_k, rr, latencies, misses = 0, [], [], []
    for item in qs:
        t0 = time.perf_counter()
        results = s.search(item["q"], k=k, mode=mode)
        latencies.append((time.perf_counter() - t0) * 1000)
        rank = next(
            (i for i, h in enumerate(results, 1) if any(_covers(e, h.section_id) for e in item["expect"])), None
        )
        if rank:
            hits_at_k += 1
            rr.append(1 / rank)
        else:
            rr.append(0.0)
            misses.append({"q": item["q"], "got": [h.section_id for h in results[:3]]})
    lat = sorted(latencies)
    return {
        "set": qset,
        "mode": mode,
        "k": k,
        "questions": len(qs),
        "recall_at_k": round(hits_at_k / len(qs), 3),
        "mrr": round(statistics.mean(rr), 3),
        "latency_ms_p50": round(lat[len(lat) // 2], 1),
        "latency_ms_p95": round(lat[min(len(lat) - 1, int(len(lat) * 0.95))], 1),
        "misses": misses,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--mode", default="hybrid", choices=["hybrid", "full_text", "embedding"])
    ap.add_argument("--set", default="dev", choices=sorted(SETS))
    a = ap.parse_args()
    print(json.dumps(evaluate(a.k, a.mode, a.set), indent=2))
